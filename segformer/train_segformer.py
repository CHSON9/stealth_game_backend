import os
import torch
from torch.utils.data import DataLoader
from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation

from segformer.person_dataset import PersonSegDataset


def train():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", device)

    model_name = "nvidia/segformer-b0-finetuned-ade-512-512"

    processor = SegformerImageProcessor(
        do_resize=True,
        size={"height": 512, "width": 512},
        do_reduce_labels=False
    )

    id2label = {0: "background", 1: "person"}
    label2id = {"background": 0, "person": 1}

    model = SegformerForSemanticSegmentation.from_pretrained(
        model_name,
        num_labels=2,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True
    ).to(device)

    train_dataset = PersonSegDataset("./data", "train", processor)
    val_dataset = PersonSegDataset("./data", "val", processor)

    train_loader = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        num_workers=0,
        drop_last=True,
        pin_memory=True
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=8,
        shuffle=False,
        num_workers=0,
        drop_last=False,
        pin_memory=True
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5, weight_decay=1e-4)

    save_dir = "weights/segformer_person"
    os.makedirs(save_dir, exist_ok=True)

    best_val = 1e9

    for epoch in range(15):
        model.train()
        train_loss_sum = 0.0

        for i, batch in enumerate(train_loader):
            pixel_values = batch["pixel_values"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(pixel_values=pixel_values, labels=labels)
            loss = outputs.loss

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss_sum += loss.item()

            if i % 100 == 0:
                print(f"[train] epoch {epoch} batch {i} loss {loss.item():.4f}")

        train_loss = train_loss_sum / max(len(train_loader), 1)

        model.eval()
        val_loss_sum = 0.0

        with torch.no_grad():
            for batch in val_loader:
                pixel_values = batch["pixel_values"].to(device)
                labels = batch["labels"].to(device)

                outputs = model(pixel_values=pixel_values, labels=labels)
                val_loss_sum += outputs.loss.item()

        val_loss = val_loss_sum / max(len(val_loader), 1)

        print(f"epoch {epoch} | train_loss {train_loss:.4f} | val_loss {val_loss:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            model.save_pretrained(save_dir)
            processor.save_pretrained(save_dir)
            print("best model saved")


if __name__ == "__main__":
    train()