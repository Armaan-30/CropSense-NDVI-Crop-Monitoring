"""Service layer.

Layering (deliberate, so Earth Engine stays replaceable):

``gee_service``
    The only module that owns Earth Engine *authentication, client lifecycle,
    collection access, cloud masking, compositing, region reduction and tile
    generation*. All ``ee.EEException`` handling and error translation lives
    here.

``ndvi_service``
    Index math, health classification, visualisation parameters and legends.
    Builds Earth Engine expressions; delegates every client concern (evaluation,
    tile registration) to ``gee_service``.

``analysis_service``
    Orchestration. Sequences the pipeline for each endpoint, batches Earth
    Engine round trips, and assembles responses.

``metrics``
    Pure Python. Statistics parsing, area arithmetic, trend fitting and warning
    generation, with no ``ee`` import at all - so the numeric logic is unit
    testable without credentials or network access.
"""
