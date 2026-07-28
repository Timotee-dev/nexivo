"""
Custom Cloudinary storage backend that inherits from Django's Storage base class.
"""
import logging
import os

from django.core.files.storage import Storage

logger = logging.getLogger("nexivo")


class CloudinaryStorage(Storage):
    """
    Django storage backend that uploads files to Cloudinary.
    """

    def _save(self, name, content):
        try:
            import cloudinary.uploader
            content.seek(0)
            folder = os.path.dirname(name) or "nexivo"
            result = cloudinary.uploader.upload(
                content.read(),
                folder=folder,
                resource_type="auto",
                overwrite=True,
            )
            url = result.get("secure_url", "")
            logger.info("Cloudinary upload success: %s -> %s", name, url)
            return url
        except Exception as e:
            logger.error("Cloudinary upload FAILED for %s: %s", name, e)
            raise

    def url(self, name):
        if not name:
            return ""
        return name

    def exists(self, name):
        return False

    def delete(self, name):
        try:
            import cloudinary.uploader
            if "cloudinary.com" in str(name):
                public_id = name.split("/upload/")[-1].rsplit(".", 1)[0]
                cloudinary.uploader.destroy(public_id)
        except Exception:
            pass

    def _open(self, name, mode='rb'):
        import urllib.request
        from django.core.files.base import ContentFile
        with urllib.request.urlopen(name) as r:
            return ContentFile(r.read(), name=name)

    def size(self, name):
        return 0

    def get_accessed_time(self, name):
        from django.utils import timezone
        return timezone.now()

    def get_created_time(self, name):
        from django.utils import timezone
        return timezone.now()

    def get_modified_time(self, name):
        from django.utils import timezone
        return timezone.now()

    def listdir(self, path):
        return [], []

    def path(self, name):
        raise NotImplementedError("CloudinaryStorage does not support path()")