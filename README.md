# CHEK Data completeness checking service

This service can perform data completeness and geometry validation operations on CityJSON / CityGML datasets.

This is a [FastAPI](https://fastapi.tiangolo.com/) application which uses
TU Delft's [val3dity](https://github.com/tudelft3d/val3dity/) to validate geometries,
[SHACL](https://www.w3.org/TR/shacl/)-based profiles to validate data completeness,
and [CityGML tools](https://github.com/citygml4j/citygml-tools) to convert CityGML files to CityJSON.

The resulting service is compatible with [OGC API - Processes](https://docs.ogc.org/is/18-062r2/18-062r2.html),
conforming the following classes:

* Core
* JSON
* OGC Process Description

A separate process is defined for each of the validation profiles found on the data source. A list of the 
available processes can be retrieved by querying the `/processes` endpoint. 

## Quick-start

### Python

If you want to run the application locally, you need to have [val3dity](https://github.com/tudelft3d/val3dity/) and
[CityGML tools](https://github.com/citygml4j/citygml-tools) installed as well.

```shell
# Create and activate virtual environment
python -m venv venv
. venv/bin/activate

# Install dependencies 
python -m pip install -r requirements.txt

# Run the application
VAL3DITY=/path/to/val3dity CITYGML_TOOLS=/path/to/citygml-tools fastapi run  # or 'fastapi dev' for development mode
```

You may also create a `.env` file with the [configuration](#configuration) instead of defining the variables.  

### Docker

val3dity and CityGML tools come prepackaged in the Docker image, so no dependencies are required.  

```
docker run dockerogc/chek-data-completeness
```

## Configuration

The application can be configured by using environment variables and/or a `.env` file (with the former taking
precedence). The following (case-insensitive) configuration variables are available:

| Variable      | Default value                      | Description                                                                                                                                                   |
|---------------|------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| data_source   | `./data/chek-profiles.ttl`         | Data source for profiles. Can be a path or a URL to a Turtle file containing the definition of the profiles, or a SPARQL endpoint URL prefixed with `sparql:` |
| val3dity      | `/opt/val3dity/val3dity`           | Path to [val3dity](https://github.com/tudelft3d/val3dity/) executable                                                                                         |
| citygml_tools | `/opt/citygml-tools/citygml-tools` | Path to [CityGML tools](https://github.com/citygml4j/citygml-tools) executable                                                                                |
| temp_dir      | `./tmp`                            | Directory where temporary files will be stored                                                                                                                |

## Defining profiles

A profile is composed of:

* An RDF description.
* One or more artifacts for validation (SHACL files).

The RDF descriptions for the profiles can be stored in a file (local or remote) or in a SPARQL endpoint
(see [Configuration](#configuration)). Each profile can then declare one or more resources (files with SHACL shapes)
for validation.

The following example shows how to describe a profile:

```ttl
@prefix chekp: <urn:chek:profiles/> .
@prefix prof: <http://www.w3.org/ns/dx/prof/> .
@prefix dct:  <http://purl.org/dc/terms/> .
@prefix role: <http://www.w3.org/ns/dx/prof/role/> .
@prefix sd: <https://w3id.org/okn/o/sd#> .
@prefix hydra: <http://www.w3.org/ns/hydra/core#> .

chekp:sample a prof:Profile, chekp:Profile ;     # Only instances of checkp:Profile are processed, so this is required 
  dct:title "Sample profile for CHEK" ;          # A title for the profile
  dct:hasVersion "0.1" ;                         # Profile version 
  prof:isProfileOf chekp:chek ;                  # prof:isProfile of can be used for declaring inheritance
  prof:hasToken "chek-ascoli-piceno" ;           # A token is required and will be used to identify the profile
  prof:hasResource [                             # At least one resource must be described
    a prof:ResourceDescriptior ;
    prof:hasRole role:validation ;                         # The role must be role:validation
    dct:format <https://w3id.org/mediatype/text/turtle> ;  # Optional
    dct:conformsTo <https://www.w3.org/TR/shacl/> ;        # Conforming to https://www.w3.org/TR/shacl/ is *mandatory* 
    prof:hasArtifact <./ap-shapes.shacl> ;                 # Path or URL to SHACL shapes file
  ] ;
  sd:hasParameter [                             # Zero or more parameters can also be declared
    dct:identifier "myParameter" ;                # Identifier that will be used when running validations
    dct:description "Sample argument" ;           # An optional description for the parameter
    sd:hasDataType "string" ;                     # Data type of the parameter
    hydra:required false ;                        # Whether the parameter is required (true) or optional (false)
  ] ;
.
```

### Profile inheritance

`prof:isProfileOf` can be used to define an inheritance chain. If a profile is declared to be the profile of
another, the validation SHACL shapes in the latter will be included any time that the former is used. This allows
defining fine-grained rules for specific cases (e.g., cities, areas, building types, etc.) while leveraging already
existing sets of rules. For example, given the following profile hierarchy:

* Italy
  * Marche region
    * Ascoli Piceno province
      * Ascoli Piceno municipality
        * Ascoli Piceno Old town
      * Ancona province

A validation run against the "Ascoli Piceno Old town" profile will include the rules for "Ascoli Piceno municipality",
"Ascoli Piceno Province", "Marche region" and "Italy".

### Using parameters

There are situations in which some information may be required at runtime to perform some type of validation. For
example, the geographical extent of a dataset may be defined by using a radius from a point of interest, but while
the radius is fixed and thus can be declared in the SHACL shape, the central point of interest depends on the
specific area that needs to be validated. 

Profiles can define parameters that will be used when running validations. Every parameter needs to have, at least:

* an identifier (`dct:identifier`) that will be used as a variable name when executing validation processes.
* a description (`dct:description`) for users to know the purpose of the parameter.
* a data type (`sd:hasDataType`).
* optionally, a flag to mark the parameter as required (`hydra:required`).

#### Parameters in SHACL shapes

When performing validations, parameter values are added to the RDF input data with the following format:

```turtle
@prefix dct: <http://purl.org/dc/terms/> .
@prefix sd: <https://w3id.org/okn/o/sd#> .

[] a sd:Parameter ;                            # Instance of Parameter
  dct:identifier "myParameter" ;               # Identifier declared in the profile definition also with dct:identifier
  sd:hasFixedValue "Value for the parameter" ; # The value provided by the user
```

*Example*: Checking that a building exists with a given identifier passed as a string:

```ttl
<#PointOfInterest>
  a sh:NodeShape ;
  sh:targetNode _:dummy ;
  sh:not [
    sh:sparql [
      sh:select """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX sd: <https://w3id.org/okn/o/sd#>
        PREFIX dct: <http://purl.org/dc/terms/>
        PREFIX city: <http://example.com/vocab/city/>
        SELECT $this (rdf:type as ?path) (?buildingOfInterest as ?value) WHERE {
          
          # Extract the parameter value from the graph
          ?buildingOfInterestParam a sd:Parameter ;
            dct:identifier "buildingOfInterest" ;
            sd:hasFixedValue ?buildingOfInterestValue ;
          .
          
          # Use the parameter value
          ?dataset city:hasObject/dct:identifier ?objectIdentifier .
          FILTER(?objectIdentifier = ?buildingOfInterestValue)
        }
      """ ;
      sh:message "Invalid point of interest" ;
      sh:severity sh:Violation ;
    ]
  ]
.

```

#### Providing parameter values

When executing processes, parameter values are passed along the inputs:

```
POST /processes/my-profile/execution

{
  "inputs": {
    "cityFiles": [
      {
        "name": "dataset1",
        "data_str": "..."
      }
    ],
    "myParameter": "Value for the parameter",
    "myOtherParameter": "Value for the second parameter"
  }
}
```
