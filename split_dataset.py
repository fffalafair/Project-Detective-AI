import os
import shutil
import random
import glob

source_dirs = ["data_backup", "data"]
target_dir = "data_clean"

splits = ["train", "val", "test"]

def get_image_label_pairs(src_dir):
    """
    Finds all valid unique image and label pairs from a given source directory.
    """
    pairs = []
    img_extensions = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]
    
    for split in splits:
        img_folder = os.path.join(src_dir, "images", split)
        lbl_folder = os.path.join(src_dir, "labels", split)
        
        if not os.path.exists(img_folder) or not os.path.exists(lbl_folder):
            continue
            
        # Use a set to prevent duplicate matches due to case-insensitive Windows globbing
        img_files = set()
        for ext in img_extensions:
            for f in glob.glob(os.path.join(img_folder, ext)):
                img_files.add(os.path.abspath(f))
            
        for img_path in sorted(list(img_files)):
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            label_path = os.path.join(lbl_folder, base_name + ".txt")
            
            if os.path.exists(label_path):
                pairs.append((img_path, label_path))
                
    return pairs

def main():
    print("=== Dataset Splitter (70% Train, 20% Val, 10% Test) ===")
    
    # Choose source directory
    source_dir = None
    max_pairs = -1
    pairs = []
    
    for src in source_dirs:
        if os.path.exists(src):
            p = get_image_label_pairs(src)
            print(f"[*] Found {len(p)} unique pairs in '{src}'")
            if len(p) > max_pairs:
                max_pairs = len(p)
                source_dir = src
                pairs = p
                
    if not source_dir or len(pairs) == 0:
        print("[-] Error: No source directories with image-label pairs found.")
        return
        
    print(f"[+] Using '{source_dir}' as source with {len(pairs)} unique pairs.")
    
    # 2. Shuffle pairs
    random.seed(42)
    random.shuffle(pairs)
    
    # 3. Calculate split sizes
    total_pairs = len(pairs)
    train_size = int(total_pairs * 0.70)
    val_size = int(total_pairs * 0.20)
    test_size = total_pairs - train_size - val_size
    
    print(f"[*] Split Target Counts:")
    print(f"  - Train (70%): {train_size} images")
    print(f"  - Val (20%): {val_size} images")
    print(f"  - Test (10%): {test_size} images")
    
    train_pairs = pairs[:train_size]
    val_pairs = pairs[train_size:train_size+val_size]
    test_pairs = pairs[train_size+val_size:]
    
    target_splits = {
        "train": train_pairs,
        "val": val_pairs,
        "test": test_pairs
    }
    
    # 4. Clear target dir if it exists to ensure 100% clean splits
    if os.path.exists(target_dir):
        print(f"[*] Cleaning up old {target_dir} folder...")
        shutil.rmtree(target_dir, ignore_errors=True)
        
    # 5. Copy files to clean target dir with folder-prefix to prevent collisions
    for split_name, pairs_list in target_splits.items():
        img_dest_dir = os.path.join(target_dir, "images", split_name)
        lbl_dest_dir = os.path.join(target_dir, "labels", split_name)
        
        os.makedirs(img_dest_dir, exist_ok=True)
        os.makedirs(lbl_dest_dir, exist_ok=True)
        
        print(f"[*] Copying {len(pairs_list)} files to {target_dir}/{split_name} split...")
        for img_src, lbl_src in pairs_list:
            # Extract parent folder name (e.g., 'train', 'val', 'test') as unique prefix
            parent_folder = os.path.basename(os.path.dirname(img_src))
            new_img_name = f"{parent_folder}_{os.path.basename(img_src)}"
            new_lbl_name = f"{parent_folder}_{os.path.basename(lbl_src)}"
            
            shutil.copy(img_src, os.path.join(img_dest_dir, new_img_name))
            shutil.copy(lbl_src, os.path.join(lbl_dest_dir, new_lbl_name))
            
    print(f"\n[+] Dataset successfully split at 70/20/10 in folder '{target_dir}'.")

if __name__ == "__main__":
    main()
