import torch
from ml.src.oiltrace_ml.metrics import binary_metrics

def test_perfect_prediction():
    targets = torch.tensor([[[[1.,0.],[0.,1.]]]])
    logits = torch.tensor([[[[20.,-20.],[-20.,20.]]]])
    m = binary_metrics(logits, targets)
    assert m["dice"] > 0.999
    assert m["iou"] > 0.999
