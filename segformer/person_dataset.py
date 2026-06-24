import os
from PIL import Image
from torch.utils.data import Dataset


class PersonSegDataset(Dataset):
    def __init__(self, root, split, processor):
        self.image_dir = os.path.join(root, "images", split)
        self.mask_dir = os.path.join(root, "masks", split)
        self.files = sorted(os.listdir(self.image_dir))
        self.processor = processor

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        name = self.files[idx]

        img_path = os.path.join(self.image_dir, name)
        mask_path = os.path.join(self.mask_dir, name.rsplit(".", 1)[0] + ".png")

        image = Image.open(img_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")

        # 0/255 -> 0/1
        mask = mask.point(lambda p: 1 if p > 0 else 0)

        encoded = self.processor(
            images=image,
            segmentation_maps=mask,
            return_tensors="pt"
        )

        return {
            "pixel_values": encoded["pixel_values"].squeeze(0),
            "labels": encoded["labels"].squeeze(0)
        }