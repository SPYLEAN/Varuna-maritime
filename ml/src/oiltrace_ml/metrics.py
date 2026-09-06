from __future__ import annotations
import torch


def dice_loss(logits, targets, eps=1e-6):
    probs = torch.sigmoid(logits)
    intersection = (probs * targets).sum(dim=(1,2,3))
    denom = probs.sum(dim=(1,2,3)) + targets.sum(dim=(1,2,3))
    dice = (2 * intersection + eps) / (denom + eps)
    return 1 - dice.mean()


def binary_confusion_counts(logits, targets, threshold=0.5):
    preds = (torch.sigmoid(logits) >= threshold).float()
    return {
        "tp": int((preds * targets).sum().item()),
        "fp": int((preds * (1 - targets)).sum().item()),
        "fn": int(((1 - preds) * targets).sum().item()),
    }


def segmentation_metrics_from_counts(tp, fp, fn, eps=1e-6):
    dice = (2*tp + eps) / (2*tp + fp + fn + eps)
    iou = (tp + eps) / (tp + fp + fn + eps)
    precision = (tp + eps) / (tp + fp + eps)
    recall = (tp + eps) / (tp + fn + eps)
    return {"dice": dice, "iou": iou, "precision": precision, "recall": recall}


def binary_metrics(logits, targets, threshold=0.5, eps=1e-6):
    counts = binary_confusion_counts(logits, targets, threshold=threshold)
    return segmentation_metrics_from_counts(**counts, eps=eps)
