# SpeechMix

Explore different way to mix speech model(wav2vec2, hubert) and nlp model(BART,T5,GPT) together.

## Installation

### pip install

```sh
pip install speechmix
```

### Build from source

git clone and cd into this project.

```sh
pip install -e .
```

## Basic Version

```sh
#####################################################~~~~~~~~~~~~~~~~~~~~~~~~~~~
python train.py \
  --speech_model_config wav2vec2           ` # Speech model architecture ` \
  --nlp_model_config    facebook/bart-base ` # Text model architexture   ` \
  --SpeechMixEED                           ` # Mixing Method             ` \
  \
  --dataset     librispeech_asr \
  --train_split train.100       \
  --field       clean           \
  --test_split  validation      \
  \
  --batch      4                \
  --grad_accum 20               \
  --epoch      30               \
  --lr         4e-5             \
  \
  --warmup_steps      500       \
  --share_layer_ratio 0         \
  --down_scale        1         \
  \
  --wandb                       \
  --worker 15                   \
  #
```

## downscale 2/4/8

```sh
python train.py \
  --speech_model_config wav2vec2           \
  --nlp_model_config    facebook/bart-base \
  --SpeechMixEED                           \
  --dataset             librispeech_asr    \
  --field               clean              \
  --train_split         train.100          \
  --test_split          validation         \
  --batch               4                  \
  --grad_accum          20                 \
  --epoch               30                 \
  --worker              15                 \
  --share_layer_ratio   0                  \
  --down_scale          2                  \
  --lr                  4e-5               \
  --warmup_steps        500                \
  --wandb                                  \
  #
```

```sh
python train.py \
  --speech_model_config wav2vec2           \
  --nlp_model_config    facebook/bart-base \
  --SpeechMixEED                           \
  --dataset             librispeech_asr    \
  --field               clean              \
  --train_split         train.100          \
  --test_split          validation         \
  --batch               4                  \
  --grad_accum          20                 \
  --epoch               30                 \
  --worker              15                 \
  --share_layer_ratio   0                  \
  --down_scale          4                  \
  --lr                  4e-5               \
  --warmup_steps        500                \
  --wandb                                  \
  #
```

```sh
python train.py \
  --speech_model_config  wav2vec2           \
  --nlp_model_config     facebook/bart-base \
  --SpeechMixEED                            \
  --dataset              librispeech_asr    \
  --field                clean              \
  --train_split          train.100          \
  --test_split           validation         \
  --batch                4                  \
  --grad_accum           20                 \
  --epoch                30                 \
  --worker               15                 \
  --share_layer_ratio    0                  \
  --down_scale           8                  \
  --lr                   4e-5               \
  --warmup_steps         500                \
  --wandb                                   \
  #
```
