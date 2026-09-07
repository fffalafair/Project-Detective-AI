import os
import sys
import subprocess
import cv2
from ultralytics import YOLO

def install_and_import(package):
    """Installs a python package if not present."""
    try:
        __import__(package)
    except ImportError:
        print(f"[*] Installing required package: {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Make sure yt-dlp is installed for streaming YouTube videos
install_and_import("yt_dlp")

import yt_dlp

def get_latest_weights():
    """
    Finds the latest best.pt weight file in the project run folders.
    """
    import glob
    # Search all possible directories where the custom weights could be saved
    weight_files = glob.glob("runs/detect/industrial_safety_yolo/yolo11s_safety_boots*/weights/best.pt")
    if not weight_files:
        weight_files = glob.glob("industrial_safety_yolo/yolo11s_safety_boots*/weights/best.pt")
    if not weight_files:
        weight_files = glob.glob("runs/detect/train*/weights/best.pt")
        
    if weight_files:
        # Return the latest folder based on modification time
        latest_file = max(weight_files, key=os.path.getmtime)
        return latest_file
    return None

def get_youtube_stream(url):
    """
    Uses yt-dlp to extract the direct stream URL from a YouTube video.
    """
    print(f"[*] Fetching YouTube stream URL for: {url}...")
    
    # Try different format specifications, including video-only formats since we don't need audio
    formats_to_try = [
        'bestvideo[ext=mp4]/bestvideo',
        'best[ext=mp4]/best',
        '136',
        '134',
        'best'
    ]
    
    for fmt in formats_to_try:
        ydl_opts = {
            'format': fmt,
            'quiet': True,
            'no_warnings': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'url' in info:
                    print(f"[+] Successfully extracted stream using format: {fmt}")
                    return info['url']
        except Exception as e:
            continue
            
    print(f"[-] Error extracting stream URL for {url}")
    return None

def is_image_url(url):
    """Checks if the given string/URL is an image source."""
    lower_url = url.lower()
    if os.path.exists(url) and any(lower_url.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']):
        return True
    for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.jfif']:
        if ext in lower_url:
            return True
    # Support Google search image thumbnails / other common CDN links
    if 'gstatic.com/images' in lower_url or 'q=tbn:' in lower_url or 'tbn=' in lower_url:
        return True
    if 'googleusercontent.com' in lower_url:
        return True
    return False

def download_image(url):
    """Downloads an online image or loads a local image."""
    if os.path.exists(url):
        return cv2.imread(url)
    try:
        import urllib.request
        import numpy as np
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as resp:
            image_bytes = np.asarray(bytearray(resp.read()), dtype="uint8")
            image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
            return image
    except Exception as e:
        print(f"[-] Error downloading/reading image: {e}")
        return None

def run_inference(youtube_url, max_frames=300):
    # Find latest trained weights
    weights_path = get_latest_weights()
    if not weights_path or not os.path.exists(weights_path):
        print("[-] Error: Trained weights 'best.pt' not found. Please run training first.")
        # Fallback to pre-trained weights for testing
        weights_path = "yolo11s.pt"
        print(f"[!] Warning: Falling back to default pre-trained '{weights_path}' weights.")
    else:
        print(f"[+] Loaded custom trained weights: {weights_path}")
        
    model = YOLO(weights_path)
    
    # Check if the input is a single image
    if is_image_url(youtube_url):
        print(f"[*] Input detected as a single image. Running image inference...")
        frame = download_image(youtube_url)
        if frame is None:
            print("[-] Error: Could not download or load image.")
            return
            
        height, width = frame.shape[:2]
        
        # Run YOLO inference
        results = model(frame, verbose=False)
        annotated_frame = frame.copy()
        
        # Parse detections and draw custom styled boxes
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                
                label_name = model.names[cls_id]
                if cls_id == 3: # Boots
                    color = (0, 255, 0) # Green
                    thickness = 2
                elif cls_id == 10: # no_boots
                    color = (0, 0, 255) # Red
                    thickness = 3
                elif cls_id == 6: # Person
                    color = (255, 255, 0) # Cyan
                    thickness = 1
                else:
                    color = (200, 200, 200) # Gray
                    thickness = 1
                    
                cv2.rectangle(annotated_frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), color, thickness)
                caption = f"{label_name} {conf:.2f}"
                cv2.putText(annotated_frame, caption, (xyxy[0], xyxy[1] - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                            
        output_filename = "output_safety_image.png"
        cv2.imwrite(output_filename, annotated_frame)
        print(f"[+] Processed image saved successfully to: {os.path.abspath(output_filename)}")
        
        # Display window
        try:
            disp_width = 800
            disp_height = int(height * (disp_width / width))
            display_frame = cv2.resize(annotated_frame, (disp_width, disp_height))
            print("[*] Displaying result image. Press any key in the window to close...")
            cv2.imshow("YOLO11s Safety Scanner - Result Image", display_frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        except Exception as e:
            print(f"[!] Warning: Could not display window: {e}")
            pass
        return

    # Get YouTube stream
    stream_url = get_youtube_stream(youtube_url)
    if not stream_url:
        print("[-] Failed to open YouTube stream.")
        return
        
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print("[-] Error: Cannot open video stream.")
        return
        
    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    if fps == 0:
        fps = 25
        
    output_filename = "output_youtube_safety.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))
    
    print(f"\n[*] Starting inference processing...")
    print(f"[*] Output video will be saved as '{output_filename}' ({width}x{height} @ {fps}fps)")
    
    frame_count = 0
    while cap.isOpened() and frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_count += 1
        if frame_count % 30 == 0:
            print(f" - Processing frame {frame_count}/{max_frames}...")
            
        # Run YOLO inference
        results = model(frame, verbose=False)
        annotated_frame = frame.copy()
        
        # Parse detections and draw custom styled boxes
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                
                # Check if the class is Boots (ID 3) or no_boots (ID 10) or Person (ID 6)
                # We can highlight Boots in Green, no_boots in Red, and keep others standard.
                label_name = model.names[cls_id]
                
                if cls_id == 3: # Boots
                    color = (0, 255, 0) # Green
                    thickness = 2
                elif cls_id == 10: # no_boots
                    color = (0, 0, 255) # Red
                    thickness = 3
                elif cls_id == 6: # Person
                    color = (255, 255, 0) # Cyan
                    thickness = 1
                else:
                    color = (200, 200, 200) # Gray
                    thickness = 1
                    
                # Draw bounding box
                cv2.rectangle(annotated_frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), color, thickness)
                # Label text
                caption = f"{label_name} {conf:.2f}"
                cv2.putText(annotated_frame, caption, (xyxy[0], xyxy[1] - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
        # Write frame to output video file
        out.write(annotated_frame)
        
        # Display window locally (if UI session available)
        try:
            # Resize display window to a comfortable width of 800px (keeps aspect ratio)
            disp_width = 800
            disp_height = int(height * (disp_width / width))
            display_frame = cv2.resize(annotated_frame, (disp_width, disp_height))
            cv2.imshow("YOLO11s Safety Scanner - Press 'q' to Quit", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        except Exception:
            # Running in headless environment, ignore cv2.imshow
            pass
            
    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print(f"\n[+] Video processing finished. Total processed: {frame_count} frames.")
    print(f"[+] Output saved successfully to: {os.path.abspath(output_filename)}")

if __name__ == "__main__":
    # Default test video: "Factory workers entry" or similar public clip.
    default_url = "https://youtu.be/Mol0lrRBy3g?si=d9vGMyrPoL9cOV39" # Man walk cycle reference video
    
    import argparse
    parser = argparse.ArgumentParser(description="Run YOLO inference on a YouTube video.")
    parser.add_argument("--url", type=str, default=default_url, help="YouTube video URL")
    parser.add_argument("--frames", type=int, default=300, help="Max frames to process (default: 300)")
    args = parser.parse_args()
    
    run_inference(args.url, max_frames=args.frames)
