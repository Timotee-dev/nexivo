"""
Custom Cloudinary storage backend for Django 6.
Uses unsigned uploads to avoid signature issues.
"""
import logging
import os

from django.core.files.storage import Storage

logger = logging.getLogger("nexivo")


class CloudinaryStorage(Storage):

    def _save(self, name, content):
        try:
            import cloudinary
            import cloudinary.uploader

            logger.info("CloudinaryStorage._save: %s | cloud=%s", name, cloudinary.config().cloud_name)

            if hasattr(content, 'seek'):
                content.seek(0)
            data = content.read() if hasattr(content, 'read') else content

            folder = os.path.dirname(name) or "nexivo"

            result = cloudinary.uploader.upload(
                data,
                folder=folder,
                resource_type="auto",
            )
            url = result.get("secure_url", "")
            logger.info("Cloudinary upload SUCCESS: %s", url)
            return url
        except Exception as e:
            logger.error("Cloudinary upload FAILED: %s", e)
            raise

    def url(self, name):
        return name or ""

    def exists(self, name):
        return False

    def delete(self, name):
        pass

    def _open(self, name, mode='rb'):
        import urllib.request
        from django.core.files.base import ContentFile
        with urllib.request.urlopen(name) as r:
            return ContentFile(r.read(), name=name)

    def size(self, name):
        return 0

    def listdir(self, path):
        return [], []

    def path(self, name):
        raise NotImplementedError("CloudinaryStorage does not support path()")