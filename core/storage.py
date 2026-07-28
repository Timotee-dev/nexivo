"""
Custom Cloudinary storage backend for Django 6.
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
            
            logger.info("CloudinaryStorage._save called for: %s", name)
            logger.info("Cloudinary config: cloud=%s", cloudinary.config().cloud_name)
            
            # Read file content as bytes
            if hasattr(content, 'seek'):
                content.seek(0)
            data = content.read() if hasattr(content, 'read') else content

            folder = os.path.dirname(name) or "nexivo"
            
            result = cloudinary.uploader.upload(
                data,
                folder=folder,
                resource_type="auto",
                overwrite=True,
                use_filename=True,
                unique_filename=True,
            )
            url = result.get("secure_url", "")
            logger.info("Cloudinary upload SUCCESS: %s", url)
            return url
        except Exception as e:
            logger.error("Cloudinary upload FAILED: %s", e)
            raise

    def url(self, name):
        if not name:
            return ""
        return name

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