import os
import re
import sys
import json
import logging
import argparse
import subprocess
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Platform(Enum):
    YOUTUBE = auto()
    INSTAGRAM = auto()
    TIKTOK = auto()
    TWITTER = auto()
    FACEBOOK = auto()
    DAILYMOTION = auto()
    VIMEO = auto()
    UNKNOWN = auto()

class DownloadType(Enum):
    VIDEO = auto()
    AUDIO = auto()
    POST = auto()
    STORY = auto()
    PROFILE_PIC = auto()
    HIGHLIGHTS = auto()

@dataclass
class DownloadConfig:
    url: str
    platform: Platform
    download_type: Optional[DownloadType] = None
    output_dir: Path = Path.cwd()
    quality: str = "best"
    format: Optional[str] = None
    cookies_file: Optional[Path] = None
    metadata: bool = True
    subtitles: bool = False
    thumbnail: bool = True
    sponsorblock: bool = False
    concurrent_fragments: int = 1
    retries: int = 10
    rate_limit: Optional[str] = None
    proxy: Optional[str] = None

class Downloader:
    """Enterprise-grade multi-platform downloader using yt-dlp"""
    
    YT_DLP_PATH = "yt-dlp"
    COOKIES_FILE = "insta.txt"
    SUPPORTED_PLATFORMS = {
        "youtube.com": Platform.YOUTUBE,
        "youtu.be": Platform.YOUTUBE,
        "instagram.com": Platform.INSTAGRAM,
        "tiktok.com": Platform.TIKTOK,
        "twitter.com": Platform.TWITTER,
        "x.com": Platform.TWITTER,
        "facebook.com": Platform.FACEBOOK,
        "fb.watch": Platform.FACEBOOK,
        "dailymotion.com": Platform.DAILYMOTION,
        "dai.ly": Platform.DAILYMOTION,
        "vimeo.com": Platform.VIMEO
    }
    
    def __init__(self, config: DownloadConfig):
        self.config = config
        self.validate_config()
        
    @classmethod
    def detect_platform(cls, url: str) -> Platform:
        """Detect platform from URL"""
        domain = urlparse(url).netloc.lower()
        for key, platform in cls.SUPPORTED_PLATFORMS.items():
            if key in domain:
                return platform
        return Platform.UNKNOWN
    
    def validate_config(self):
        """Validate download configuration"""
        if not self.config.url:
            raise ValueError("URL cannot be empty")
            
        if self.config.platform == Platform.UNKNOWN:
            raise ValueError(f"Unsupported URL: {self.config.url}")
            
        if not self.config.output_dir.exists():
            self.config.output_dir.mkdir(parents=True, exist_ok=True)
            
        if self.config.cookies_file and not self.config.cookies_file.exists():
            raise FileNotFoundError(f"Cookies file not found: {self.config.cookies_file}")
    
    def build_yt_dlp_command(self) -> List[str]:
        """Construct yt-dlp command based on configuration"""
        cmd = [self.YT_DLP_PATH]
        
        # Basic options
        cmd.extend([
            "--no-playlist",
            "--ignore-errors",
            "--retries", str(self.config.retries),
            "--concurrent-fragments", str(self.config.concurrent_fragments),
            "--progress",
            "--newline",
            "--console-title",
        ])
        
        # Output template
        output_template = self.get_output_template()
        cmd.extend(["-o", output_template])
        
        # Format selection
        if self.config.format:
            cmd.extend(["-f", self.config.format])
        else:
            cmd.extend(["-f", self.get_default_format()])
        
        # Rate limiting
        if self.config.rate_limit:
            cmd.extend(["--limit-rate", self.config.rate_limit])
        
        # Proxy
        if self.config.proxy:
            cmd.extend(["--proxy", self.config.proxy])
        
        # Get the appropriate cookies file
        cookies_file = None
        if self.config.cookies_file and self.config.cookies_file.exists():
            cookies_file = self.config.cookies_file
        elif (self.config.platform == Platform.YOUTUBE and 
            Path(self.COOKIES_FILE).exists()):
            cookies_file = Path(self.COOKIES_FILE)

        # Add cookies to command if available
        if cookies_file:
            cmd.extend(["--cookies", str(cookies_file)])
        elif self.config.platform == Platform.INSTAGRAM:
            cmd.extend(["--cookies-from-browser", "chrome"])
        
        # Add the URL at the end
        cmd.append(self.config.url)
        
        return cmd
    
    def get_output_template(self) -> str:
        """Generate output template based on platform and type"""
        templates = {
            Platform.YOUTUBE: "%(title)s [%(id)s].%(ext)s",
            Platform.INSTAGRAM: "%(uploader)s - %(title)s [%(id)s].%(ext)s",
            Platform.TIKTOK: "%(uploader)s - %(title)s [%(id)s].%(ext)s",
            Platform.TWITTER: "%(uploader)s - %(title)s [%(id)s].%(ext)s",
            Platform.FACEBOOK: "%(title)s [%(id)s].%(ext)s",
            Platform.DAILYMOTION: "%(title)s [%(id)s].%(ext)s",
            Platform.VIMEO: "%(title)s [%(id)s].%(ext)s",
        }
        
        base_template = templates.get(self.config.platform, "%(title)s [%(id)s].%(ext)s")
        
        if self.config.download_type == DownloadType.AUDIO:
            return os.path.join(str(self.config.output_dir), "Audio", base_template)
        return os.path.join(str(self.config.output_dir), "Video", base_template)
    
    def get_default_format(self) -> str:
        """Get default format based on download type"""
        if self.config.download_type == DownloadType.AUDIO:
            return "bestaudio/best"
        
        format_map = {
            Platform.YOUTUBE: "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            Platform.INSTAGRAM: "best",
            Platform.TIKTOK: "best",
            Platform.TWITTER: "best",
            Platform.FACEBOOK: "best",
            Platform.DAILYMOTION: "best",
            Platform.VIMEO: "best",
        }
        
        return format_map.get(self.config.platform, "best")
    
    def download(self) -> bool:
        """Execute the download process"""
        cmd = self.build_yt_dlp_command()
        logger.info(f"Executing command: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Real-time progress output
            for line in process.stdout:
                line = line.strip()
                if line:
                    logger.info(line)
            
            process.wait()
            
            if process.returncode != 0:
                error_output = process.stderr.read()
                logger.error(f"Download failed with error: {error_output}")
                return False
                
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Download failed with error: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during download: {str(e)}")
            return False

class BatchDownloader:
    """Handle batch downloads from file or list of URLs"""
    
    def __init__(self, downloader_class=Downloader):
        self.downloader_class = downloader_class
    
    def download_batch(self, urls: List[str], config: DownloadConfig, max_workers: int = 4) -> Dict[str, bool]:
        """Download multiple URLs concurrently"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._download_single, url, config): url
                for url in urls
            }
            
            for future in as_completed(futures):
                url = futures[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    logger.error(f"Error downloading {url}: {str(e)}")
                    results[url] = False
        
        return results
    
    def _download_single(self, url: str, config: DownloadConfig) -> bool:
        """Download a single URL"""
        download_config = DownloadConfig(
            url=url,
            platform=config.platform if config.platform != Platform.UNKNOWN else self.downloader_class.detect_platform(url),
            download_type=config.download_type,
            output_dir=config.output_dir,
            quality=config.quality,
            format=config.format,
            cookies_file=config.cookies_file,
            metadata=config.metadata,
            subtitles=config.subtitles,
            thumbnail=config.thumbnail,
            sponsorblock=config.sponsorblock,
            concurrent_fragments=config.concurrent_fragments,
            retries=config.retries,
            rate_limit=config.rate_limit,
            proxy=config.proxy
        )
        
        downloader = self.downloader_class(download_config)
        return downloader.download()

def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Enterprise Multi-Platform Downloader",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Input options
    input_group = parser.add_argument_group("Input Options")
    input_group.add_argument(
        "urls",
        nargs="*",
        help="URL(s) to download (can be multiple)"
    )
    input_group.add_argument(
        "--input-file",
        type=Path,
        help="File containing URLs to download (one per line)"
    )
    
    # Download options
    dl_group = parser.add_argument_group("Download Options")
    dl_group.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "downloads",
        help="Directory to save downloads"
    )
    dl_group.add_argument(
        "--type",
        type=str,
        choices=["video", "audio", "post", "story", "profile-pic", "highlights"],
        help="Type of content to download"
    )
    dl_group.add_argument(
        "--format",
        type=str,
        help="Format code or quality specification"
    )
    dl_group.add_argument(
        "--quality",
        type=str,
        default="best",
        help="Quality preference (best, 1080p, etc.)"
    )
    
    # Platform options
    platform_group = parser.add_argument_group("Platform Options")
    platform_group.add_argument(
        "--platform",
        type=str,
        choices=["youtube", "instagram", "tiktok", "twitter", "facebook", "dailymotion", "vimeo", "auto"],
        default="auto",
        help="Platform to download from"
    )
    
    platform_group.add_argument(
        "--cookies",
        type=Path,
        help="Path to cookies file for authentication"
    )
    
    # Network options
    net_group = parser.add_argument_group("Network Options")
    net_group.add_argument(
        "--proxy",
        type=str,
        help="Proxy to use for downloads"
    )
    net_group.add_argument(
        "--rate-limit",
        type=str,
        help="Download rate limit (e.g. 50K or 4.2M)"
    )
    net_group.add_argument(
        "--retries",
        type=int,
        default=10,
        help="Number of retries for failed downloads"
    )
    net_group.add_argument(
        "--concurrent",
        type=int,
        default=1,
        help="Number of concurrent fragments to download"
    )
    
    # Metadata options
    meta_group = parser.add_argument_group("Metadata Options")
    meta_group.add_argument(
        "--metadata",
        action="store_true",
        help="Download metadata (disabled by default)"
    )
    meta_group.add_argument(
        "--subtitles",
        action="store_true",
        help="Download subtitles/closed captions (disabled by default)"
    )
    meta_group.add_argument(
        "--thumbnail",
        action="store_true",
        help="Download thumbnail (disabled by default)"
    )
    meta_group.add_argument(
        "--sponsorblock",
        action="store_true",
        help="Use SponsorBlock for YouTube videos"
    )
    
    # Batch options
    batch_group = parser.add_argument_group("Batch Options")
    batch_group.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent downloads for batch processing"
    )
    
    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_args()
    
    # Collect URLs from both arguments and input file
    urls = args.urls.copy()
    if args.input_file:
        try:
            with open(args.input_file, 'r') as f:
                urls.extend(line.strip() for line in f if line.strip() and not line.startswith('#'))
        except Exception as e:
            logger.error(f"Error reading input file: {str(e)}")
            sys.exit(1)
    
    if not urls:
        logger.error("No URLs provided")
        sys.exit(1)
    
    # Map platform string to enum
    platform_map = {
        "youtube": Platform.YOUTUBE,
        "instagram": Platform.INSTAGRAM,
        "tiktok": Platform.TIKTOK,
        "twitter": Platform.TWITTER,
        "facebook": Platform.FACEBOOK,
        "dailymotion": Platform.DAILYMOTION,
        "vimeo": Platform.VIMEO,
        "auto": Platform.UNKNOWN
    }
    
    # Map type string to enum
    type_map = {
        "video": DownloadType.VIDEO,
        "audio": DownloadType.AUDIO,
        "post": DownloadType.POST,
        "story": DownloadType.STORY,
        "profile-pic": DownloadType.PROFILE_PIC,
        "highlights": DownloadType.HIGHLIGHTS
    }
    
    # Create download config
    config = DownloadConfig(
        url="",  # Will be set for each URL in batch download
        platform=platform_map[args.platform],
        download_type=type_map.get(args.type) if args.type else None,
        output_dir=args.output_dir,
        quality=args.quality,
        format=args.format,
        cookies_file=args.cookies,
        metadata=False,  # Disable metadata by default
        subtitles=False,  # Disable subtitles by default
        thumbnail=False,  # Disable thumbnail by default
        sponsorblock=args.sponsorblock,
        concurrent_fragments=args.concurrent,
        retries=args.retries,
        rate_limit=args.rate_limit,
        proxy=args.proxy
    )
    
    # Execute downloads
    batch_downloader = BatchDownloader()
    results = batch_downloader.download_batch(urls, config, max_workers=args.workers)
    
    # Print summary
    successful = sum(1 for result in results.values() if result)
    logger.info(f"\nDownload summary:")
    logger.info(f"Total URLs: {len(results)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {len(results) - successful}")
    
    if successful < len(results):
        logger.info("\nFailed URLs:")
        for url, success in results.items():
            if not success:
                logger.info(f"- {url}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)