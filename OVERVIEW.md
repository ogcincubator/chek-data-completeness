# How the CHEK Data Completeness Validator Works

The CHEK validator checks whether a 3D city dataset — provided in CityJSON or CityGML format — meets a specific set of quality requirements. These requirements are grouped into **profiles**, and the service runs two kinds of checks: **geometry validation** and **data completeness validation**.

## What is a profile?

A profile is a named collection of rules that describes what a valid dataset must look like for a particular context. For example, a profile for a specific city or region might require that every building has a roof, a ground footprint, and a defined height — while a more general national profile might only require the footprint.

Profiles can build on each other. A profile for a specific neighbourhood can inherit all the rules from its city, which in turn inherits from its region and country. This means that validating against a fine-grained local profile automatically includes all the broader rules up the chain.

## What happens when you validate a dataset?

1. **Upload**: You submit one or more city files along with the name of the profile you want to validate against.
2. **Format conversion** *(if needed)*: CityGML files are automatically converted to CityJSON before processing.
3. **Geometry check**: The 3D geometry of each object in the dataset is checked for validity — for example, that surfaces are closed, that volumes are correctly oriented, and that there are no self-intersections.
4. **Data completeness check**: The dataset is checked against the profile's rules to verify that all required attributes and relationships are present and correctly structured.
5. **Report**: You receive a report listing any violations found, along with the objects and attributes that caused them.

## What does "data completeness" mean?

Beyond geometry, city datasets often need to carry specific semantic information to be useful — things like building use, construction date, or energy-related attributes. "Data completeness" means that this information is present, correctly typed, and consistent with what the profile requires. The rules are expressed using SHACL, a standard W3C language for validating RDF-based data, which allows profiles to define precise, machine-readable constraints.

## Who defines the profiles?

Profiles are defined externally and loaded into the service at startup. They can live in a local file, a remote URL, or a SPARQL endpoint. This means the validator is not tied to any fixed set of rules — it can be pointed at different profile registries depending on the deployment context.
