# OilTrace AI — SIH 26143 Backend/ML Starter

Backend-first starter for SAR oil-spill segmentation, evaluation, inference, and geospatial mask export.

## Tonight's target
1. Validate paired SAR images/masks.
2. Train a small U-Net baseline on Colab GPU.
3. Evaluate Dice/IoU/Precision/Recall.
4. Run inference on unseen images.
5. Export a predicted mask; if the source is a georeferenced raster, convert it to GeoJSON.

## Quick start (Colab/Linux)
```bash
git clone <your-repo-url>
cd oiltrace-ai
pip install -r requirements.txt
python -m ml.src.oiltrace_ml.validate --images /content/data/images --masks /content/data/masks
python -m ml.src.oiltrace_ml.train --images /content/data/images --masks /content/data/masks --epochs 5 --batch-size 8 --out models/oiltrace_unet_smoke.pt
python -m ml.src.oiltrace_ml.infer --checkpoint models/oiltrace_unet_smoke.pt --image /content/data/images/example.png --out /content/pred_mask.png
```

See `docs/COLAB_QUICKSTART.md` for the recommended smoke-test workflow.
