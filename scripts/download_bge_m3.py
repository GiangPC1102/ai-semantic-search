#!/usr/bin/env python3
"""
Script to download BGE-M3 model locally for Mem0Service
This script downloads the complete BGE-M3 model from Hugging Face Hub
and saves it to the local directory for offline use.
"""

import sys
import argparse
from pathlib import Path
from huggingface_hub import snapshot_download
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Silence noisy HTTP/HF loggers so the console only shows our own progress
for _noisy in ("httpx", "httpcore", "huggingface_hub", "urllib3", "filelock"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

def download_bge_m3_model(model_name="BAAI/bge-m3", save_path="ai_models/bge-m3", force_download=False):
    """
    Download BGE-M3 model from Hugging Face Hub to local directory.
    
    Args:
        model_name (str): Hugging Face model name
        save_path (str): Local directory to save the model
        force_download (bool): Force re-download even if directory exists
    """
    
    # Convert to Path object
    save_path = Path(save_path)
    
    # Check if directory already exists
    if save_path.exists() and not force_download:
        logger.info(f"Model directory {save_path} already exists.")
        logger.info("Use --force to re-download or remove the directory manually.")
        return True
    
    # Remove existing directory if force download
    if save_path.exists() and force_download:
        logger.info(f"Removing existing directory: {save_path}")
        import shutil
        shutil.rmtree(save_path)
    
    try:
        logger.info(f"Downloading {model_name} to {save_path}...")
        
        # Download the entire repository
        snapshot_download(
            repo_id=model_name,
            local_dir=str(save_path),
        )
        
        logger.info("Download completed successfully!")
        
        # List downloaded files
        logger.info("Files in bge-m3 directory:")
        for file in sorted(save_path.iterdir()):
            if file.is_file():
                size = file.stat().st_size
                size_mb = size / (1024 * 1024)
                if size_mb > 1:
                    logger.info(f"  {file.name} ({size_mb:.1f} MB)")
                else:
                    logger.info(f"  {file.name} ({size} bytes)")
            else:
                logger.info(f"  {file.name}/ (directory)")
        
        # Verify critical files
        critical_files = [
            "pytorch_model.bin",
            "config.json", 
            "tokenizer.json",
            "sentencepiece.bpe.model",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "modules.json"
        ]
        
        missing_files = []
        for file in critical_files:
            if not (save_path / file).exists():
                missing_files.append(file)
        
        if missing_files:
            logger.error(f"Missing critical files: {missing_files}")
            return False
        else:
            logger.info("All critical files are present!")
            
        # Check pytorch_model.bin size (should be ~2.27GB)
        pytorch_model = save_path / "pytorch_model.bin"
        if pytorch_model.exists():
            size_gb = pytorch_model.stat().st_size / (1024 * 1024 * 1024)
            if size_gb > 2.0:  # Should be around 2.27GB
                logger.info(f"Model weights file size: {size_gb:.2f} GB (correct)")
            else:
                logger.warning(f"Model weights file size: {size_gb:.2f} GB (might be incomplete)")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Download BGE-M3 model for Mem0Service")
    parser.add_argument("--model", default="BAAI/bge-m3", help="Hugging Face model name")
    parser.add_argument("--output", default="ai_models/bge-m3", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    parser.add_argument("--test", action="store_true", help="Test model loading after download")
    
    args = parser.parse_args()
    
    logger.info("Starting BGE-M3 model download...")
    logger.info(f"Model: {args.model}")
    logger.info(f"Output: {args.output}")
    
    # Download model
    success = download_bge_m3_model(
        model_name=args.model,
        save_path=args.output,
        force_download=args.force
    )
    
    if not success:
        logger.error("Download failed!")
        sys.exit(1)
    
    logger.info("BGE-M3 model download completed successfully!")
    logger.info("You can now use this model with Mem0Service in offline mode.")

if __name__ == "__main__":
    main()
