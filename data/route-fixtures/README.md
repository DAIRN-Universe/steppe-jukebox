# Route regression fixtures

The two JSON examples retain geographic cell keys and provenance from the
cancelled water-routing experiment. They are used to verify that v0.6.0
connects those interior cells directly, without consulting any water mask.
The historical `blocked` classifications are not current evidence of water
or land: scientific quality flags were not validated in that prototype.

Downloaded PNG tiles/manifests in the local `nasa/` folder are ignored and
are not shipped with the application or release. Tests only need the JSON
cell keys. Current routing enforces region boundaries and holes, with no
restriction based on water or unknown water coverage.
