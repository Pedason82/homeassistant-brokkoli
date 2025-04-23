# Brokkoli Plant Management for Home Assistant

> **Note**
> 
> This project is based on the work of [@Olen](https://github.com/Olen) and his "Alternative plants component" integration.
> 
> All credit for the original development goes to the original author.

<!-- 
TODO: Add new images to the dingausmwald/homeassistant-brokkoli repository.
Image placeholders are marked with TODO comments throughout the document.
-->

This integration can automatically fetch data from [Seedfinder](https://github.com/dingausmwald/homeassistant-seedfinder).

# BREAKING CHANGES

>**Warning**
>
> **This integration is *not* compatible with the original plant integration in HA.**

Plants are set up in the UI and all configuration of your plants can be managed there or by automations and scripts.

## Plants are now treated as _devices_

This means that the main plant entity references other entities, and they are grouped togheter in the GUI as a single device.

<!-- TODO: Add screenshot showing plant device overview -->

This also means that this version is _not_ compatible with earlier releases from this repository, or with the "plant" integration that is part of your default Home Assistant installation 

## Highlights 

### Use the UI to set up plant devices
* Config Flow is used to set up the plants

<!-- TODO: Add GIF showing Config Flow setup process -->

* This works both with and without Seedfinder

### Better handling of thresholds

* Plant images and information like flowering duration are fetched automatically from Seedfinder if available
* All thresholds now are their own entities and their values can be changed from the UI or by scripts and automations.
* These changes are instantly reflected in HA. No need to restart to change the thresholds.

<!-- TODO: Add screenshots showing threshold configuration -->

* Max and min temperature is now dependent on the unit of measurement - currently °C and °F is supported.
  * The values will be updated if you change your units in the Home Assistant settings

### Easier to replace sensors

* You can use a service call to replace the different sensors used to monitor the plant

<!-- TODO: Add screenshot of service call interface -->

What I personally do, to make a clearer separation between the physical sensor and the sensor that is part of the plant, is that all my _physical_ sensors (e.g BLE-devices) have generic entity_ids like `sensor.ble_sensor_1_moisture`, `sensor.ble_sensor_1_illumination`, `sensor.ble_sensor_2_conductivity` etc.
And all my plants sensors have entity_ids like `sensor.rose_moisture`, `sensor.chili_conductivity` etc.

That way, if I need to replace a (physical) sensor for e.g. my "Rose" plant, it is very easy to grasp the concept and use
```
service: plant.replace_sensor
data:
  meter_entity: sensor.rose_illumination
  new_sensor: sensor.ble_sensor_12_illumination
```

* The new sensor values are immediately picked up by the plant integration without any need to restart

### Better handling of species, image and plant information

* If you change the species of a plant in the UI, new data are fetched from Seedfinder
* You can optionally select to force a refresh of plant data from Seedfinder, even if you do not change the species.  
* Images and information like flowering duration can be updated from the UI
* You can chose to disable problem triggers on all sensors.

<!-- TODO: Add screenshot of species configuration -->

These updates are immediately reflected in HA without restarting anything.

### Daily Light Integral

* A new Daily Light Integral - DLI - sensor is created for all plants. 

<!-- TODO: Add screenshot of DLI sensor -->

See https://en.wikipedia.org/wiki/Daily_light_integral for what DLI means

### More flexible lovelace card

* The Lovelace flower card makes use of the integration, and is very flexible.

<!-- TODO: Add screenshots of flower card -->

* The flower card also handles both °C and °F

## Dependencies

* [Updated Lovelace Flower Card](https://github.com/Olen/lovelace-flower-card/tree/new_plant)

* [Seedfinder integration](https://github.com/dingausmwald/homeassistant-seedfinder)

Seedfinder is not a strict requirement, but a strong recommendation. Without the Seedfinder integration, you need to set images and information like flowering duration manually. With the Seedfinder integration added, all data is fetched automatically, and it makes setting up and maintaining plants much, much easier.   

# Installation

### Install and set up Seedfinder

_Not required, but strongly recommended_

* Install the Seedfinder integration: https://github.com/dingausmwald/homeassistant-seedfinder 
* Set it up, and add your client_id and secret, and test it by using e.g. the `seedfinder.search` service call to search for something.   

### Install new flower-card for Lovelace

_Currently this is the only card in lovelace that support this integration.  Feel free to fork and update - or create PRs - for other lovelace cards._ 

* Install verson 2 of the Flower Card from https://github.com/Olen/lovelace-flower-card/


### Install this integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

#### Via HACS
* Add this repo as a ["Custom repository"](https://hacs.xyz/docs/faq/custom_repositories/) with type "Integration"
* Click "Install" in the new "Brokkoli Plant Management" card in HACS.
* Install
* Restart Home Assistant

#### Manual Installation
* Copy the entire `custom_components/plant/` directory to your server's `<config>/custom_components` directory
* Restart Home Assistant

> **Note**
> This integration uses the same component name as the built-in plant integration to override it. This ensures proper functionality while providing enhanced features.

After Home Assistant is restarted, you will find all your plants under "Settings" - "Devices and Services" - "Devices".  It will take a minute or two before the current values start to update.

> **Warning**
> The `entity_id` of your plants will probably have changed from the old integration to the new one.  This means that any automations, scripts etc. that use the entity_id or reacts to changes in your plants status will need to be updated.  You probably also need to change the way you read data from the plant device in any such components.

> **Warning**
> This integration is NOT compatible with the built in original plant component.  This means that e.g. the plant cards etc. in the UI, and any blueprints etc. that are built for the original plant intergation wil NOT work with this version.

## Problem reports
By default, all problems (e.g. every time a sensor reports a value that is above or below the threshold set in "limits"), the plant state will be set to "problem".

This can be adjusted under "Settings" -> "Devices and Services" -> "Plant Monitor" -> "Your Plant Name" and "Configure".

<!-- TODO: Add screenshot of problem reports configuration -->

Here you can select what kind of threshold violations should trigger a "problem" state of the plant entity.

## Fetching data from Seedfinder

_This requires the [Seedfinder integration](https://github.com/dingausmwald/homeassistant-seedfinder) to be installed._

When you set up a new plant, the configuration flow will search Seedfinder for the species you enter. If any matches are found, you are presented with a list of exact species to choose from. Be aware that the Seedfinder API does currently not include any of your private user defined species, so you will not find them in the list. See below for how to refresh data from Seedfinder.
If no matches are found, the configuration flow will continue directly to the next step.

In the following step, plant information and images from Seedfinder are pre-filled and displayed. If you chose the incorrect species, you can uncheck the _"This is the plant I was looking for"_ checkbox, and you will be directed back to the dropdown of species to select another one.
If no match is found in Seedfinder, you'll need to provide your own information and images.

If the species is found in Seedfinder, the image link is pre-filled with the URL there. You may override this with your own links. Both links starting with `http` and local images in your "www"-folder, e.g. `/local/...` are supported.

### Changing the species / refreshing data

If you later want to change the species of a plant, you do that under "Configuration" of the selected device.

"Settings" -> "Devices and Services" -> "Plant Monitor" -> "Your Plant Name" and "Configure".

<!-- TODO: Add screenshot of species configuration -->

From there, you have the option to set a new species. If you change the species, data for the new species will be automatically fetched from Seedfinder. The species will have to be entered **exactly** as the "pid" in Seedfinder (including any punctations etc.). If the species is found in Seedfinder, the information is updated with the new values. Also, if the current image links to Seedfinder or the image link is empty, the URL to the image in Seedfinder is added. If the current image points to a local file, or a different URL, the image is **not** replaced unless "Force refresh" is checked. The "Species to display" is not changed if you change the species unless "Force refresh" is checked.
If no species are found in Seedfinder, the information and image will be retained with their current values. 

If you just want to refresh the data from Seedfinder, without changing the species - for instance if you have private species defined in Seedfinder that are not found during setup, you check the "Force refresh" checkbox, and data will be fetched from Seedfinder without needing to change the species. If this checkbox is checked, both the image and the "Species to display" is updated if the species is found in Seedfinder.
If no species is found in Seedfinder, nothing is changed. 

## FAQ

### I added the wrong sensors, and after removing and adding the plant again with the correct sensor, I can still see the wrong values from the old sensor.

Home Assistant is _very_ good at remembering old configuration of entities if new entities with the same name as the old ones are added again.  This means that if you first create e.g. a moisture-sensor for your plant that reads the data from `sensor.bluetooth_temperature_xxxx`, and the remove the plant and add it back again with the same name, but with moisture-sensor set to `sensor.xiaomi_moisture_yyyy` you might experience that the plant will still show data from the old sensor.  Instead of removing and re-adding a plant, you should just use the `replace_sensor` service call to add the new sensor.

<!-- 
Original credits:
<a href="https://www.buymeacoffee.com/olatho" target="_blank">
<img src="https://user-images.githubusercontent.com/203184/184674974-db7b9e53-8c5a-40a0-bf71-c01311b36b0a.png" style="height: 50px !important;"> 
</a>
-->

