"""
Custom Cloudinary storage backend that bypasses django-cloudinary-storage.
Uses the cloudinary SDK directly for reliable file uploads.
"""
import io
import os

import cloudinary
import cloudinary.uploader
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryStorage(Storage):
    def _upload(self, name, content):
        folder = os.path.dirname(name)
        public_id = os.path.splitext(os.path.basename(name))[0]
        result = cloudinary.uploader.upload(
            content,
            folder=folder,
            public_id=public_id,
            overwrite=True,
            resource_type="auto",
        )
        return result

    def _save(self, name, content):
        content.seek(0)
        result = self._upload(name, content)
        return result.get("public_id", name)

    def url(self, name):
        if not name:
            return ""
        if name.startswith("http"):
            return name
        try:
            result = cloudinary.CloudinaryImage(name).build_url()
            return result
        except Exception:
            return name

    def exists(self, name):
        try:
            cloudinary.api.resource(name)
            return True
        except Exception:
            return False

    def delete(self, name):
        try:
            cloudinary.uploader.destroy(name)
        except Exception:
            pass

    def size(self, name):
        try:
            result = cloudinary.api.resource(name)
            return result.get("bytes", 0)
        except Exception:
            return 0

    def listdir(self, path):
        return [], []