import os
import sys
import argparse
from typing import Dict, List, Union, Optional

from dataclasses import dataclass

import torch

from datasets import (load_dataset, 
                      Audio, 
                      load_from_disk)
from transformers import (Trainer, 
                          TrainingArguments, 
                          EarlyStoppingCallback, 
                          AutoTokenizer, 
                          TrainerCallback, 
                          TrainerState, 
                          TrainerControl)

import asrp
import speechmix


class FreezingCallback(TrainerCallback):
    def __init__(self, trainer, freeze_model, freeze_epoch=3):
        self.trainer = trainer
        self.freeze_model = freeze_model
        self.freeze_epoch = freeze_epoch
        self.current_step_idx = 0
        self.default_param_fix = {}
        self.name_list = []
        for name, param in self.freeze_model.named_parameters():
            self.name_list.append(name)
            self.default_param_fix[name] = param.requires_grad
        self.freeze_layers = int(len(self.default_param_fix.keys()) / freeze_epoch)

    def on_epoch_begin(self, 
        args: TrainingArguments, 
        state: TrainerState, 
        control: TrainerControl, 
        **kwargs
    ):
        if state.epoch < self.freeze_epoch:
            release = self.name_list[-int(self.freeze_layers * state.epoch):]
            for name, param in self.freeze_model.named_parameters():
                if name in release:
                    param.requires_grad = True
                else:
                    param.requires_grad = False
        else:
            for name, param in self.freeze_model.named_parameters():
                param.requires_grad = self.default_param_fix[name]
        self.current_step_idx += 1

    def on_save(
        self, 
        args: TrainingArguments, 
        state: TrainerState, 
        control: TrainerControl, 
        **kwargs
    ):
        for name, param in self.trainer.model.named_parameters():
            param.requires_grad = True

@dataclass
class DataCollatorWithPadding:
    tokenizer: AutoTokenizer
    padding: Union[bool, str] = True
    max_length: Optional[int] = None
    max_length_labels: Optional[int] = None
    pad_to_multiple_of: Optional[int] = None
    pad_to_multiple_of_labels: Optional[int] = None
    selftype: bool = False

    def __call__(
        self, 
        features: List[Dict[str, 
        Union[List[int], 
        torch.Tensor]]]
    ) -> Dict[str, torch.Tensor]:
        batch = {}
        batch['input_values'] = [torch.tensor(feature["input_values"]) for feature in features]
        label_features = [{"input_ids": feature['labels']} for feature in features]

        labels_batch = self.tokenizer.pad(
            label_features,
            padding=self.padding,
            max_length=self.max_length_labels,
######################################################~~~~~~~~~~~~~~~~~~~~~~~~~~
            pad_to_multiple_of=self.pad_to_multiple_of_labels,
            return_tensors="pt",
        )

        if 'text_input_ids' in features[0]:
            text_features = [{"input_ids": feature['text_input_ids']} for feature in features]
            text_batch = self.tokenizer.pad(
                text_features,
                padding=self.padding,
                max_length=self.max_length_labels,
                pad_to_multiple_of=self.pad_to_multiple_of_labels,
                return_tensors="pt",
            )
            batch['text_input_ids'] = text_batch['input_ids']
        labels_batch = labels_batch['input_ids'].masked_fill(labels_batch.attention_mask.ne(1), -100)

        # if bos token is appended in previous tokenization step,
        # cut bos token here as it's append later anyway
        if (labels_batch[:, 0] == self.tokenizer.bos_token_id).all().cpu().item():
            labels_batch = labels_batch[:, 1:]

        batch['labels'] = labels_batch

        torch.cuda.empty_cache()
        return batch

def compute_metrics(pred):
    global model
    try: model
    except NameError as e: 
        raise AssertionError("Please initialize a model!")

    pred_ids = pred.predictions
    pred_ids = [i[i != -100] for i in pred_ids]
    pred_str = model.tokenizer.batch_decode(pred_ids, skip_special_tokens=True, group_tokens=False)
    # we do not want to group tokens when computing the metrics
    label_ids = pred.label_ids
    label_ids = [i[i != -100] for i in label_ids]
    label_str = model.tokenizer.batch_decode(label_ids, skip_special_tokens=True, group_tokens=False)
    # for l, p in zip(label_str, pred_str):
    #     print(l, "======", p)
    cer = asrp.cer(label_str, pred_str)
    wer = asrp.wer(label_str, pred_str)
    return {"cer": cer, "wer": wer}

def prepare_dataset(batch, selftype=False):
    global model
    try: model
    except NameError as e: 
        raise AssertionError("Please initialize a model!")

    audio = batch["audio"]
    batch["input_values"] = audio["array"]
    batch["length"] = batch["input_values"].size
    sent = batch["text"] if 'text' in batch else batch["sentence"]
    sent = sent.lower()
    gen_input = model.tokenizer(sent, add_special_tokens=False).input_ids
    if selftype:
        predicted = [model.decoder_model.config.decoder_start_token_id]
        with torch.no_grad():
            model.decoder_model.eval()
            for _ in range(model.decoder_model.config.max_length):
                max_item = torch.argmax(
                    model.decoder_model(input_ids=torch.tensor([gen_input], device=model.device),
                                        output_hidden_states=True,
                                        decoder_input_ids=torch.tensor(
                                            [predicted],
                                            device=model.device)).logits, -1)[:, -1].item()
                if model.decoder_model.config.eos_token_id == max_item:
                    break
                predicted.append(max_item)
        batch["text_input_ids"] = gen_input
        batch['labels'] = predicted[1:]
    else:
        batch['labels'] = gen_input
    batch['labels'] += [model.tokenizer.eos_token_id]
    batch["input_ids"] = batch["labels"]
    return batch

def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--speech_model_config", type=str)
    parser.add_argument("--nlp_model_config", type=str)
    parser.add_argument("--SpeechMixEED", action='store_true')
    parser.add_argument("--SpeechMixED", action='store_true')
    parser.add_argument("--SpeechMixSelf", action='store_true')
    parser.add_argument("--SpeechMixAdapt", action='store_true')
    parser.add_argument("--SpeechMixGAN", action='store_true')
    parser.add_argument("--SpeechMixFixed", action='store_true')
    parser.add_argument("--HFSpeechMixEED", action='store_true')
    parser.add_argument("--HFSpeechMixED", action='store_true')
    parser.add_argument("--HFSpeechMixSelf", action='store_true')
    parser.add_argument("--HFSpeechMixAdapt", action='store_true')
    parser.add_argument("--HFSpeechMixGAN", action='store_true')
    parser.add_argument("--HFSpeechMixFixed", action='store_true')
    parser.add_argument("--dataset", type=str)
    parser.add_argument("--field", type=str)
    parser.add_argument("--train_split", type=str)
    parser.add_argument("--test_split", type=str)
    parser.add_argument("--notes", type=str)
    parser.add_argument("--grad_accum", default=3, type=int)
    parser.add_argument("--logging_steps", default=10, type=int)
    parser.add_argument("--warmup_steps", default=10, type=int)
    parser.add_argument("--save_total_limit", default=2, type=int)
    # parser.add_argument("--max_grad_norm", default=10, type=int)
    parser.add_argument("--worker", default=10, type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--epoch", default=1000, type=int)
    parser.add_argument("--lr", type=float)
    parser.add_argument("--eval_step", default=700, type=int)
    parser.add_argument('--share_layer_ratio', default=0, type=float)
    parser.add_argument('--down_scale', default=8, type=int)
    parser.add_argument('--weighted_sum', action='store_true')
    parser.add_argument('--fixed_parameters', action='store_true')
    parser.add_argument('--fixed_except', nargs='+',
                        default=["layer_norm", "encoder_attn", 'enc_to_dec_proj', 'length_adapter',
                                    "layernorm_embedding", 'attention', 'encoder'])
    parser.add_argument("--fp16", action='store_true')
    parser.add_argument("--wandb", action='store_true')

    input_arg, model_arg = parser.parse_known_args(args)
    input_arg = {k: v for k, v in vars(input_arg).items() if v is not None}
    other_arg = {k.replace("--", ""): v for k, v in zip(model_arg[:-1:2], model_arg[1::2])}
    return input_arg, other_arg


def main(arg=None):
    global FreezingCallback, DataCollatorWithPadding
    global compute_metrics, prepare_dataset, parse_args

    input_arg, other_arg = parse_args(sys.argv[1:]) if arg is None else parse_args(arg)
    print("input_arg", input_arg)
    # region --- model selection
    if input_arg['SpeechMixEED']:
        model_type = "SpeechMixEED"
        model = speechmix.SpeechMixEED(**input_arg)
    elif input_arg['SpeechMixFixed']:
        model_type = "SpeechMixFixed"
        model = speechmix.SpeechMixFixed(**input_arg)
    elif input_arg['SpeechMixSelf']:
        model_type = "SpeechMixSelf"
        model = speechmix.SpeechMixSelf(**input_arg)
    elif input_arg['SpeechMixGAN']:
        model_type = "SpeechMixGAN"
        model = speechmix.SpeechMixGAN(**input_arg)
    elif input_arg['SpeechMixAdapt']:
        model_type = "SpeechMixAdapt"
        model = speechmix.SpeechMixAdapt(**input_arg)
    elif input_arg['HFSpeechMixED']:
        model_type = "HFSpeechMixED"
        model = speechmix.HFSpeechMixED(**input_arg)
    elif input_arg['HFSpeechMixEED']:
        model_type = "HFSpeechMixEED"
        model = speechmix.HFSpeechMixEED(**input_arg)
    elif input_arg['HFSpeechMixFixed']:
        model_type = "HFSpeechMixFixed"
        model = speechmix.HFSpeechMixFixed(**input_arg)
    elif input_arg['HFSpeechMixSelf']:
        model_type = "HFSpeechMixSelf"
        model = speechmix.HFSpeechMixSelf(**input_arg)
    elif input_arg['HFSpeechMixGAN']:
        model_type = "HFSpeechMixGAN"
        model = speechmix.HFSpeechMixGAN(**input_arg)
    elif input_arg['HFSpeechMixAdapt']:
        model_type = "HFSpeechMixAdapt"
        model = speechmix.HFSpeechMixAdapt(**input_arg)
    else:
        model_type = "SpeechMixEED"
        model = speechmix.SpeechMixEED(**input_arg)
    # endregion --- model selection

    selftype = ('SpeechMixSelf' in model_type or 'SpeechMixGAN' in model_type)
    cache_path_train = f'./train_ds_{input_arg["dataset"]}_{input_arg["field"]}_{input_arg["train_split"]}.parquet'
    cache_path_valid = f'./valid_ds_{input_arg["dataset"]}_{input_arg["field"]}_{input_arg["train_split"]}.parquet'

    if os.path.exists(cache_path_train) and os.path.exists(cache_path_valid):
        train_ds = load_from_disk(cache_path_train)
        valid_ds = load_from_disk(cache_path_valid)
    else:
        train_ds = load_dataset(input_arg["dataset"], input_arg["field"], split=input_arg["train_split"])
        valid_ds = load_dataset(input_arg["dataset"], input_arg["field"], split=input_arg["test_split"])

        train_ds = train_ds.cast_column("audio", Audio(sampling_rate=16_000))
        valid_ds = valid_ds.cast_column("audio", Audio(sampling_rate=16_000))

        train_ds = train_ds.map(prepare_dataset, num_proc=1, fn_kwargs={"selftype": selftype})
        valid_ds = valid_ds.map(prepare_dataset, num_proc=1, fn_kwargs={"selftype": selftype})

        train_ds.save_to_disk(cache_path_train)
        valid_ds.save_to_disk(cache_path_valid)

    data_collator = DataCollatorWithPadding(tokenizer=model.tokenizer, padding=True,
                                            selftype=selftype)

    training_args = TrainingArguments(
        output_dir=f"./{input_arg['speech_model_config']}_{input_arg['nlp_model_config']}_{model_type}_{input_arg.get('notes', '')}",
        per_device_train_batch_size=int(input_arg['batch']),
        per_device_eval_batch_size=int(input_arg['batch']),
        gradient_accumulation_steps=int(input_arg['grad_accum']),
        eval_accumulation_steps=2,
        evaluation_strategy="steps",
        group_by_length=True,
        fp16=input_arg.get('fp16', True),
        load_best_model_at_end=True,
        num_train_epochs=input_arg.get('epoch', 10),
        save_steps=input_arg.get('eval_step', 700),
        eval_steps=input_arg.get('eval_step', 700),
        logging_steps=input_arg.get('logging_steps', 10),
        learning_rate=input_arg.get('lr', 5e-4),
        warmup_steps=input_arg.get('warmup_steps', 500),
        save_total_limit=input_arg.get('save_total_limit', 2),
        dataloader_num_workers=input_arg.get('worker', 10),
        report_to="wandb" if input_arg.get('wandb', True) else "none",
    )
    # some trainer problem - save all logistics on compute_metrics, cause out of memory, fix:argmax first;
    # dynamic padding on past key value, cause index error, fix: return only loss and logist
    # group_by_length took lots of time during preprocessing
    trainer = Trainer(
        model=model,
        args=training_args,
        compute_metrics=compute_metrics,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        data_collator=data_collator,
        tokenizer=model.tokenizer,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=20)],
    )

    # https://discuss.huggingface.co/t/gradual-layer-freezing/3381/4
    freezing_callback = FreezingCallback(trainer, model.encoder_model, 1000)
    trainer.add_callback(freezing_callback)

    trainer.train()


if __name__ == "__main__": main()

