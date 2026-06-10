
import numpy as np
import os
import epicure.epicuring as epi
import epicure.Utils as ut
from epicure.appose_epyseg import go_epyseg
import logging
    

def test_segment_epyseg():
    """ Segment the movie with epyseg-appose function """
    test_img = os.path.join(".", "test_data", "003_crop.tif")
    img, _, _, _, _, _ = ut.open_image(test_img, get_metadata=False, verbose=0)
    parameters = { "tile_width":256,
                  "tile_height":256,
                  "overlap_width":32,
                  "overlap_height":32,
                  "model":"epyseg default (v2)",
                  "norm_min":0,
                  "norm_max":1
                  }
    log_handler = logging.StreamHandler()
    log_handler.setLevel( logging.INFO )
    formatter = logging.Formatter('[Napari-epyseg] - %(message)s')
    log_handler.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.setLevel( logging.INFO )
    logger.propagate = False
    logger.addHandler( log_handler )
    result = go_epyseg( img, parameters, logger=logger )
    #print(result.shape)
    assert result.shape == (11,189,212)

test_segment_epyseg()
