import torch
import os
from typing import Optional
import config

try:
    from diffusers import StableDiffusionXLPipeline, AutoencoderKL
    DIFFUSERS_AVAILABLE = True
except ImportError:
    DIFFUSERS_AVAILABLE = False
    print("⚠️ Warning: diffusers not installed. Local GPU image generation disabled.")


class LocalImageGenerator:
    def __init__(self):
        self.pipe = None
        self.device = config.LOCAL_SD_DEVICE if torch.cuda.is_available() and config.LOCAL_SD_DEVICE == "cuda" else "cpu"
        
        if not DIFFUSERS_AVAILABLE:
            print("⚠️ Local image generation unavailable: diffusers not installed")
            return
            
        if not config.LOCAL_SD_ENABLED:
            print("ℹ️ Local image generation disabled in config")
            return
            
        if not os.path.exists(config.LOCAL_SD_MODEL_PATH):
            print(f"⚠️ Model path not found: {config.LOCAL_SD_MODEL_PATH}")
            print("   Place SDXL model files in this directory to enable local generation")
            return
            
        try:
            print(f"🔄 Loading local SDXL model into {self.device}...")
            
            # Try to load from single file first, then from directory
            if os.path.isfile(config.LOCAL_SD_MODEL_PATH):
                self.pipe = StableDiffusionXLPipeline.from_single_file(
                    config.LOCAL_SD_MODEL_PATH,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    use_safetensors=True
                )
            else:
                self.pipe = StableDiffusionXLPipeline.from_pretrained(
                    config.LOCAL_SD_MODEL_PATH,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                )
            
            self.pipe.to(self.device)
            
            # Enable memory efficient attention if available
            try:
                self.pipe.enable_xformers_memory_efficient_attention()
                print("   ✅ XFormers memory efficient attention enabled")
            except:
                print("   ℹ️ XFormers not available, using default attention")
            
            print(f"✅ Local SDXL model loaded successfully on {self.device}")
        except Exception as e:
            print(f"❌ Failed to load local SDXL model: {e}")
            self.pipe = None

    def is_available(self) -> bool:
        return self.pipe is not None

    def generate(self, prompt: str, negative: str = "", steps: Optional[int] = None, guidance: Optional[float] = None) -> Optional[str]:
        if not self.is_available():
            return None
            
        if not os.path.exists(config.LOCAL_SD_MODEL_PATH):
            return None
            
        try:
            num_steps = steps if steps else config.LOCAL_SD_STEPS
            guidance_scale = guidance if guidance else config.LOCAL_SD_GUIDANCE
            
            print(f"🎨 Generating image: {prompt[:50]}...")
            
            image = self.pipe(
                prompt=prompt,
                negative_prompt=negative,
                num_inference_steps=num_steps,
                guidance_scale=guidance_scale,
            ).images[0]

            # Ensure generated directory exists
            os.makedirs(os.path.join(os.path.dirname(__file__), "generated"), exist_ok=True)
            
            output_path = os.path.join(
                os.path.dirname(__file__),
                "generated",
                f"local_{abs(hash(prompt)) % 1000000}.png"
            )

            image.save(output_path)
            print(f"✅ Image saved to: {output_path}")
            return output_path
        except Exception as e:
            print(f"❌ Image generation failed: {e}")
            return None


# Singleton instance
local_gpu_gen = LocalImageGenerator()

