.. _storage-profiles:

========================
Flocker Storage Profiles
========================

.. begin-body

Flocker Storage Profiles are a way to address the storage requirements for your application, enabling you to choose the best set of service attributes from your storage provider.

For example, in a development environment you might only want a low cost storage option.
However, if you need storage for a production environment, you can choose a profile with high performance and high cost options.

Flocker Storage Profiles require support from your storage driver, and you are able to choose from the following profiles:

* Gold: This profile is suited for applications that have high performance requirements from storage.
  For example, databases.
* Silver: This profile is suited for applications that might not require such high performance. 
  Typically, this would align with default storage options.
* Bronze: This profile is suited for applications that have no requirements for performance, and therefore a low cost option can be selected.

Please be aware that the actual specification of these profiles may differ between each storage provider.
The definition for each profile should be documented in the storage providers documentation.

Currently, the following community supported drivers support Flocker Storage Profiles:

* `Dell SC Series`_
* `ConvergeIO`_
* `Hedvig`_

.. note::
	Flocker Storage Profiles is a new Flocker feature, and we're hoping to iterate on the functionality in future releases.
	If you use a Storage Profile, it would be great to :ref:`hear from you <talk-to-us>` about how it is being used and what features you would like to see in the future.

.. _Dell SC Series: https://github.com/dellstorage/storagecenter-flocker-driver/blob/master/dell_storagecenter_driver/dell_storagecenter_blockdevice.py
.. _ConvergeIO: https://github.com/ConvergeIO/cio-flocker-driver/blob/gh-pages/driver/cio.py#L133
.. _Hedvig: http://hedviginc.com/blog/flocker-storage-profiles-for-docker

.. end-body

More information about support for profiles can be found in the :ref:`configuration documentation for each backend <supported-backends>`.
