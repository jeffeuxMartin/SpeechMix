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
DOWNSAMPLE_SCALE=1  # can be 2 or 4 or 8
python train.py \
  ` # Speech model arch.      ` \
  --speech_model_config \
             wav2vec2           \
  ` # Text model architecture ` \
  --nlp_model_config    \
             facebook/bart-base \
  ` # Mixing Method           ` \
  --SpeechMixEED        \
                                \
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
  --down_scale \
            ${DOWNSAMPLE_SCALE} \
  \
  --wandb                       \
  --worker 15                   \
  #
```

```sh
#####################################################~~~~~~~~~~~~~~~~~~~~~~~~~~~
```
