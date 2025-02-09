from typing import List, Dict, Optional
import time
from threading import Timer
from llama_cpp import Llama
from llama_cpp.llama_chat_format import MoondreamChatHandler, MiniCPMv26ChatHandler

from llama_assistant.config import models


class Model:
    def __init__(
        self,
        model_type: str,
        model_id: str,
        model_name: str,
        model_path: Optional[str] = None,
        repo_id: Optional[str] = None,
        filename: Optional[str] = None,
    ):
        self.model_type = model_type
        self.model_id = model_id
        self.model_name = model_name
        self.model_path = model_path
        self.repo_id = repo_id
        self.filename = filename

    def is_online(self) -> bool:
        return self.repo_id is not None and self.filename is not None


class ModelHandler:
    def __init__(self):
        self.supported_models: List[Model] = []
        self.loaded_model: Optional[Dict] = None
        self.current_model_id: Optional[str] = None
        self.unload_timer: Optional[Timer] = None

    def list_supported_models(self) -> List[Model]:
        return self.supported_models

    def add_supported_model(self, model: Model):
        self.supported_models.append(model)

    def remove_supported_model(self, model_id: str):
        self.supported_models = [m for m in self.supported_models if m.model_id != model_id]
        if self.current_model_id == model_id:
            self.unload_model()

    def load_model(self, model_id: str) -> Optional[Dict]:
        if self.current_model_id == model_id and self.loaded_model:
            return self.loaded_model

        self.unload_model()  # Unload the current model if any

        model = next((m for m in self.supported_models if m.model_id == model_id), None)
        if not model:
            print(f"Model with ID {model_id} not found.")
            return None

        if model.is_online():
            if model.model_type == "text":
                loaded_model = Llama.from_pretrained(
                    repo_id=model.repo_id,
                    filename=model.filename,
                    n_ctx=2048,
                )
            elif model.model_type == "image":
                if "moondream2" in model.repo_id:
                    chat_handler = MoondreamChatHandler.from_pretrained(
                        repo_id="vikhyatk/moondream2",
                        filename="*mmproj*",
                    )
                    loaded_model = Llama.from_pretrained(
                        repo_id=model.repo_id,
                        filename=model.filename,
                        chat_handler=chat_handler,
                        n_ctx=2048,
                    )
                elif "MiniCPM" in model.repo_id:
                    chat_handler = MiniCPMv26ChatHandler.from_pretrained(
                        repo_id=model.repo_id,
                        filename="*mmproj*",
                    )
                    loaded_model = Llama.from_pretrained(
                        repo_id=model.repo_id,
                        filename=model.filename,
                        chat_handler=chat_handler,
                        n_ctx=2048,
                    )
            else:
                print(f"Unsupported model type: {model.model_type}")
                return None
        else:
            # Load model from local path
            loaded_model = Llama(model_path=model.model_path)

        self.loaded_model = {
            "model": loaded_model,
            "last_used": time.time(),
        }
        self.current_model_id = model_id
        self._schedule_unload()

        return self.loaded_model

    def unload_model(self):
        if self.loaded_model:
            print(f"Unloading model: {self.current_model_id}")
            self.loaded_model = None
            self.current_model_id = None
        if self.unload_timer:
            self.unload_timer.cancel()
            self.unload_timer = None

    def chat_completion(
        self,
        model_id: str,
        message: str,
        image: Optional[str] = None,
        n_ctx: int = 2048,
    ) -> str:
        model_data = self.load_model(model_id)
        if not model_data:
            return "Failed to load model"

        model = model_data["model"]
        model_data["last_used"] = time.time()
        self._schedule_unload()

        if image:
            response = model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": message},
                            {"type": "image_url", "image_url": {"url": image}},
                        ],
                    }
                ]
            )
        else:
            response = model.create_chat_completion(messages=[{"role": "user", "content": message}])

        return response["choices"][0]["message"]["content"]

    def _schedule_unload(self):
        if self.unload_timer:
            self.unload_timer.cancel()

        self.unload_timer = Timer(3600, self.unload_model)
        self.unload_timer.start()


# Example usage
handler = ModelHandler()

for model_data in models:
    model = Model(**model_data)
    handler.add_supported_model(model)

# List supported models
print("Supported models:")
for model in handler.list_supported_models():
    print(f"- {model.model_name} (ID: {model.model_id})")

if __name__ == "__main__":
    # Use text model
    result = handler.chat_completion("llama_text", "Tell me a joke")
    print(result)

    # Use image model
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
    result = handler.chat_completion("moondream", "What's in this image?", image=image_url)
    print(result)

    # Use local model
    result = handler.chat_completion("local_model", "Hello, local model!")
    print(result)
