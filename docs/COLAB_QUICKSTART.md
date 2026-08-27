# Colab quick-start — tonight smoke test

## 1. Turn on GPU
Runtime → Change runtime type → T4 GPU.

## 2. Clone repo and install
```bash
!git clone <YOUR_GITHUB_REPO_URL> /content/oiltrace-ai
%cd /content/oiltrace-ai
!pip install -q -r requirements.txt
```

## 3. Put a manageable dataset subset in Colab
Use paired image/mask folders where basenames match, e.g.:
```
/content/oil_data/images/scene_001.png
/content/oil_data/masks/scene_001.png
```
Do NOT begin with tens of gigabytes. Start with 100–300 paired samples.

## 4. Validate first
```bash
!python -m ml.src.oiltrace_ml.validate \
  --images /content/oil_data/images \
  --masks /content/oil_data/masks
```

## 5. Smoke-train 3 epochs on 150 samples
```bash
!python -m ml.src.oiltrace_ml.train \
  --images /content/oil_data/images \
  --masks /content/oil_data/masks \
  --max-samples 150 \
  --epochs 3 \
  --batch-size 8 \
  --out /content/oiltrace_smoke.pt
```
Success criteria: training runs on CUDA, loss does not explode/NaN, and validation Dice becomes non-zero.

## 6. If smoke test passes, train a longer baseline
```bash
!python -m ml.src.oiltrace_ml.train \
  --images /content/oil_data/images \
  --masks /content/oil_data/masks \
  --epochs 12 \
  --batch-size 8 \
  --out /content/oiltrace_unet_v1.pt
```

## 7. Inference
```bash
!python -m ml.src.oiltrace_ml.infer \
  --checkpoint /content/oiltrace_unet_v1.pt \
  --image /content/oil_data/images/<UNSEEN_IMAGE> \
  --out /content/pred_mask.png
```

Tonight's gate: a real unseen SAR image produces a non-trivial predicted segmentation mask plus Dice/IoU/Precision/Recall during validation.
