class ProjectMetadata:
    def __init__(self, product_name, slug, description="", price="", selling_points="", target_audience="", pain_points=""):
        self.product_name = product_name
        self.product_slug = slug
        self.description = description
        self.price = price
        self.selling_points = selling_points
        self.target_audience = target_audience
        self.pain_points = pain_points
        self.keywords = {"vi": [], "en": [], "zh": []}
        self.scripts = {
            "style": "",
            "voice_script": "",
            "caption": "",
            "hashtags": ""
        }
        self.audio = {
            "file_name": "",
            "file_path": "",
            "duration": 0.0
        }
        self.exports = {
            "final_video_path": ""
        }

    def to_dict(self):
        return {
            "product_name": self.product_name,
            "product_slug": self.product_slug,
            "description": self.description,
            "price": self.price,
            "selling_points": self.selling_points,
            "target_audience": self.target_audience,
            "pain_points": self.pain_points,
            "keywords": self.keywords,
            "scripts": self.scripts,
            "audio": self.audio,
            "exports": self.exports
        }

    @staticmethod
    def from_dict(data):
        meta = ProjectMetadata(
            product_name=data.get("product_name", ""),
            slug=data.get("product_slug", ""),
            description=data.get("description", ""),
            price=data.get("price", ""),
            selling_points=data.get("selling_points", ""),
            target_audience=data.get("target_audience", ""),
            pain_points=data.get("pain_points", "")
        )
        meta.keywords = data.get("keywords", {"vi": [], "en": [], "zh": []})
        meta.scripts = data.get("scripts", {"style": "", "voice_script": "", "caption": "", "hashtags": ""})
        meta.audio = data.get("audio", {"file_name": "", "file_path": "", "duration": 0.0})
        meta.exports = data.get("exports", {"final_video_path": ""})
        return meta
