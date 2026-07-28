"""
Custom Cloudinary storage backend.
Uses the cloudinary SDK directly for reliable file uploads.
"""
import io
import logging
import os

logger = logging.getLogger("nexivo")


class CloudinaryStorage:
    def __init__(self):
        try:
            import cloudinary
            import cloudinary.uploader
            import cloudinary.api
            self._cloudinary = cloudinary
            self._uploader = cloudinary.uploader
            self._api = cloudinary.api
            logger.info("CloudinaryStorage initialized: cloud=%s", cloudinary.config().cloud_name)
        except Exception as e:
            logger.error("CloudinaryStorage init failed: %s", e)
            self._cloudinary = None

    def _save(self, name, content):
        if not self._cloudinary:
            logger.error("Cloudinary not configured — cannot save %s", name)
            return name
        try:
            content.seek(0)
            folder = os.path.dirname(name)
            result = self._uploader.upload(
                content,
                folder=folder or "nexivo",
                resource_type="auto",
                overwrite=True,
            )
            url = result.get("secure_url", "")
            logger.info("Cloudinary upload success: %s -> %s", name, url)
            return url
        except Exception as e:
            logger.error("Cloudinary upload failed for %s: %s", name, e)
            return name

    def url(self, name):
        if not name:
            return ""
        return name

    def exists(self, name):
        return False

    def delete(self, name):
        try:
            if self._cloudinary and "cloudinary.com" in str(name):
                public_id = name.split("/upload/")[-1].rsplit(".", 1)[0]
                self._uploader.destroy(public_id)
        except Exception:
            pass

    def size(self, name):
        return 0

    def listdir(self, path):
        return [], []

    def path(self, name):
        raise NotImplementedError("CloudinaryStorage does not support path()")

    def open(self, name, mode='rb'):
        import urllib.request
        from django.core.files.base import ContentFile
        try:
            with urllib.request.urlopen(name) as r:
                return ContentFile(r.read())
        except Exception:
            raise FileNotFoundError(name)

    def save(self, name, content, max_length=None):
        return self._save(name, content)

    def get_available_name(self, name, max_length=None):
        return name

    def generate_filename(self, filename):
        return filename