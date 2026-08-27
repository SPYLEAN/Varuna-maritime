import torch
import pytest
from ml.src.oiltrace_ml.model import SmallUNet


def test_small_unet_shape():
    model = SmallUNet(in_channels=1, out_channels=1, base=16)
    x = torch.randn(2, 1, 256, 256)
    y = model(x)
    assert y.shape == (2, 1, 256, 256)


def test_small_unet_cuda_if_available():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SmallUNet().to(device)
    x = torch.randn(1, 1, 128, 128).to(device)
    y = model(x)
    assert y.device == device
    assert y.shape == (1, 1, 128, 128)
