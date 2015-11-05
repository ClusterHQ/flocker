Flocker Storage Profiles are a way to help you choose different levels of service from your storage provider.
For example, in a development environment you might only want a low cost storage option.
However, if you need storage for a production environment, you can choose a profile with high performance and high cost options.

Flocker Storage Profiles require support from your storage driver, and you are able to choose from the following profiles:

* Gold: This profile is typically for high performance storage.
* Silver: This profile is typically the intermediate, or default storage.
* Bronze: This profile is typically for low cost storage.

Please be aware that the actual specification of these profiles may differ between each storage provider.
The definition for each profile should be documented in the storage providers documentation.

Currently, only a selection of :ref:`backends supported by Flocker <supported-backends>` support Flocker Storage Profiles.
More information about support for profiles can be found in the :ref:`configuration documentation for each backend <supported-backends>`.

.. note::
	Flocker Storage Profiles is a new and exciting implementation, but it currently only has minimal features.
	If you use a Storage Profile, it would be great to :ref:`hear from you <talk-to-us>` about how you use it and what features you would like to see in future releases.
