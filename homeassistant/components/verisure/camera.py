"""Support for Verisure cameras."""
from __future__ import annotations

import errno
import os
from typing import Any, Callable

from homeassistant.components.camera import Camera
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VerisureDataUpdateCoordinator
from .const import CONF_SMARTCAM, DOMAIN, LOGGER


def setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    add_entities: Callable[[list[Entity], bool], None],
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up the Verisure Camera."""
    coordinator = hass.data[DOMAIN]
    if not int(coordinator.config.get(CONF_SMARTCAM, 1)):
        return

    directory_path = hass.config.config_dir
    if not os.access(directory_path, os.R_OK):
        LOGGER.error("file path %s is not readable", directory_path)
        return

    add_entities(
        [
            VerisureSmartcam(hass, coordinator, device_label, directory_path)
            for device_label in coordinator.get("$.customerImageCameras[*].deviceLabel")
        ]
    )


class VerisureSmartcam(CoordinatorEntity, Camera):
    """Representation of a Verisure camera."""

    coordinator = VerisureDataUpdateCoordinator

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: VerisureDataUpdateCoordinator,
        device_label: str,
        directory_path: str,
    ):
        """Initialize Verisure File Camera component."""
        super().__init__(coordinator)

        self._device_label = device_label
        self._directory_path = directory_path
        self._image = None
        self._image_id = None
        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, self.delete_image)

    def camera_image(self) -> bytes | None:
        """Return image response."""
        self.check_imagelist()
        if not self._image:
            LOGGER.debug("No image to display")
            return
        LOGGER.debug("Trying to open %s", self._image)
        with open(self._image, "rb") as file:
            return file.read()

    def check_imagelist(self) -> None:
        """Check the contents of the image list."""
        self.coordinator.update_smartcam_imageseries()
        image_ids = self.coordinator.get_image_info(
            "$.imageSeries[?(@.deviceLabel=='%s')].image[0].imageId", self._device_label
        )
        if not image_ids:
            return
        new_image_id = image_ids[0]
        if new_image_id in ("-1", self._image_id):
            LOGGER.debug("The image is the same, or loading image_id")
            return
        LOGGER.debug("Download new image %s", new_image_id)
        new_image_path = os.path.join(
            self._directory_path, "{}{}".format(new_image_id, ".jpg")
        )
        self.coordinator.session.download_image(
            self._device_label, new_image_id, new_image_path
        )
        LOGGER.debug("Old image_id=%s", self._image_id)
        self.delete_image()

        self._image_id = new_image_id
        self._image = new_image_path

    def delete_image(self) -> None:
        """Delete an old image."""
        remove_image = os.path.join(
            self._directory_path, "{}{}".format(self._image_id, ".jpg")
        )
        try:
            os.remove(remove_image)
            LOGGER.debug("Deleting old image %s", remove_image)
        except OSError as error:
            if error.errno != errno.ENOENT:
                raise

    @property
    def name(self) -> str:
        """Return the name of this camera."""
        return self.coordinator.get_first(
            "$.customerImageCameras[?(@.deviceLabel=='%s')].area", self._device_label
        )
