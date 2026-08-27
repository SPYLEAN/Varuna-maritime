import torch
import pytest
from ml.src.oiltrace_ml.metrics import binary_metrics, dice_loss


def test_perfect_prediction():
    targets = torch.tensor([[[[1.0, 0.0], [0.0, 1.0]]]])
    logits = torch.tensor([[[[20.0, -20.0], [-20.0, 20.0]]]])
    m = binary_metrics(logits, targets)
    assert m["dice"] > 0.999
    assert m["iou"] > 0.999
    assert m["precision"] > 0.999
    assert m["recall"] > 0.999


def test_zero_prediction():
    targets = torch.tensor([[[[1.0, 1.0], [1.0, 1.0]]]])
    logits = torch.tensor([[[[-20.0, -20.0], [-20.0, -20.0]]]])
    m = binary_metrics(logits, targets)
    assert m["dice"] < 0.01
    assert m["recall"] < 0.01


def test_dice_loss_bounds():
    targets = torch.tensor([[[[1.0, 0.0], [0.0, 1.0]]]])
    perfect_logits = torch.tensor([[[[20.0, -20.0], [-20.0, 20.0]]]])
    loss = dice_loss(perfect_logits, targets)
    assert loss.item() < 0.01
