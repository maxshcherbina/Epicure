import epicure.Utils as utils
import numpy as np

def test_get_skeleton():
    """ Test function get_skeleton: from a label image, get the binary skeleton """
    img = np.zeros((10, 50, 50), dtype=np.uint8)
    ## place 3 labels in the top left corner
    img[:, 0:4,  0:5] = 1  
    img[:, 4:8,  0:5] = 2 
    img[:, 8:12, 0:5] = 3 
    skel = utils.get_skeleton( img )
    ## should not be empty
    assert np.sum(skel) > 0
    ## should be binary
    assert np.max(skel) == 1
    ## should have enough positives pixels
    assert np.sum(skel) > 150
    assert np.sum(skel) < 200
    assert skel[0,0,5] == 1

def test_count_neighbor():
    """ Test function count_neighbors: for a label, count nieghboring labels """
    img = np.zeros((50, 50), dtype=np.uint8)
    ## place 3 labels in the top left corner
    img[ 0:4,  0:5] = 1  
    img[ 4:8,  0:5] = 2 
    img[ 8:12, 0:5] = 3 
    img[ 18:22, 20:25] = 4 
    nneigh = utils.count_neighbors( img, label=1 )
    assert nneigh == 1
    nneigh = utils.count_neighbors( img, label=2 )
    assert nneigh == 2
    nneigh = utils.count_neighbors( img, label=4 )
    assert nneigh == 0

def test_get_border_cells():
    """ Should return list of labels that touch the border of image """
    img = np.zeros((50, 50), dtype=np.uint8)
    ## place 3 labels in the top left corner
    img[ 0:4,  0:5] = 1  
    img[ 4:8,  1:5] = 2 
    img[ 8:12, 2:5] = 3 
    img[ 18:22, 20:25] = 4 
    borders = utils.get_border_cells( img )
    ## touch until 1
    assert 1 in borders
    assert 2 in borders
    assert 3 not in borders

def test_reset_labels():
    """ Should create unique labels accross all frames """
    img = np.zeros((10, 50, 50), dtype=np.uint8)
    ## place 3 labels in the top left corner
    img[ :,0:4,  0:5] = 1  
    img[ :,4:8,  1:5] = 2 
    img[ :,8:12, 2:5] = 3 
    img[ :,18:22, 20:25] = 4 
    labels = utils.reset_labels( img )
    assert np.max(labels) == 20


def test_velocities():
    """ Test measure of velocities """
    # dx=3, dy=4, dt=1  →  speed = 5 at every frame
    pts_pos = np.array([[0, 0, 0],
                        [1, 3, 4],
                        [2, 6, 8]], dtype=float)
    result = utils.velocities( pts_pos )
    np.testing.assert_allclose(result, 5.0 * np.ones(3))

test_get_skeleton()
test_velocities()
test_count_neighbor()



def test_velocities():
    """ Test measure of velocities """
    # dx=3, dy=4, dt=1  →  speed = 5 at every frame
    pts_pos = np.array([[0, 0, 0],
                        [1, 3, 4],
                        [2, 6, 8]], dtype=float)
    result = utils.velocities( pts_pos )
    np.testing.assert_allclose(result, 5.0 * np.ones(3))

test_get_skeleton()
test_reset_labels()
