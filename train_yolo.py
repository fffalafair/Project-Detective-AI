import argparse
import torch
from ultralytics import YOLO

def check_system():
    """
    Checks GPU/CUDA availability.
    """
    print("=== System Configuration Check ===")
    print(f"PyTorch Version: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA (GPU) Available: {cuda_available}")
    if cuda_available:
        print(f"GPU Device Name: {torch.cuda.get_device_name(0)}")
        device = 0
    else:
        print("[!] Warning: CUDA is not available. Training will run on CPU (which will be extremely slow).")
        device = "cpu"
    return device

def train_model(epochs=150, batch_size=16):
    device = check_system()
    
    print(f"\n[*] Initializing YOLO11s (YOLO11 Small) model...")
    # Load the pre-trained YOLO11s model. Ultralytics automatically downloads it on first use.
    model = YOLO("yolo11s.pt")
    
    print(f"[*] Starting training for {epochs} epochs (Batch size: {batch_size}) on device: {device}...")
    try:
        results = model.train(
            data="dataset.yaml",
            epochs=epochs,
            imgsz=640,
            batch=batch_size,
            device=device,
            workers=4,
            project="industrial_safety_yolo",
            name="yolo11s_safety_boots"
        )
        print("\n[+] Training completed successfully!")
        print(f"[+] Model weights and metrics saved under: industrial_safety_yolo/yolo11s_safety_boots/")
    except Exception as e:
        print(f"\n[-] Error during training: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train YOLO11s model on safety shoes dataset.")
    parser.add_argument("--epochs", type=int, default=150, help="Number of training epochs (default: 150)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16)")
    args = parser.parse_args()
    
    train_model(epochs=args.epochs, batch_size=args.batch)
