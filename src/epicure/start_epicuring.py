"""
   **Start EpiCure plugin**

   Open the interface to select the movie and associated segmentation to process
"""

from napari import current_viewer
from magicgui import magicgui
from napari.utils.history import get_save_history, update_save_history 
from napari.utils import progress
import pathlib
import epicure.Utils as ut
from epicure.epicuring import EpiCure
import multiprocessing
import logging


def start_from_layers():
    """ Start EpiCure from already opened image and segmentation layers """
    from typing import Union
    hist = get_save_history()
    cdir = hist[0]
    
    def show_doc():
        """ Open the online documentation """
        ut.show_documentation_page( "Start-epicure#start-from-opened-layers" )

    @magicgui(call_button="Use selected layers",
            __ = {"widget_type": "Label"},
            go_help = {"widget_type": "PushButton", "label": "Help"},
            )
    def select_layer(movie: Union["napari.layers.Image", None], movie_path: pathlib.Path, 
                     segmentation: Union["napari.layers.Layer", None], 
                    __ ="",
                     go_help=False):
        """ GUI to choose the layers to use """
        if movie == "None":
            movie = None
        segmented = segmentation
        if segmentation == "None":
            segmented = None
        ut.remove_all_widgets(viewer)
        #ut.remove_widget(viewer, "Start from opened layers")
        start_epi, epicure_instance = gui_files(movie=movie, movie_path=movie_path, segmented=segmented)
        viewer.window.add_dock_widget(start_epi)
        return start_epi

    viewer = current_viewer()
    wid = viewer.window.add_dock_widget(select_layer)
    select_layer.go_help.clicked.connect( show_doc )
    return wid
    


def start_epicure():
    """ Start EpiCure from scratch """
    gui, epicure = gui_files(movie=None, movie_path ="", segmented=None)
    return gui

def gui_files(movie=None, movie_path="", segmented=None):
    """ GUI to choose files and parameters """
    hist = get_save_history()
    cdir = hist[0]
    viewer = current_viewer()
    Epic = EpiCure(viewer)
    caxis = None
    cval = 0
    ncpus = int(multiprocessing.cpu_count()*0.5)

    def set_visibility():
        """ Visibility of the parameters in the GUI """
        if movie is not None:
            get_files.image_file.visible = False
        if segmented is not None:
            get_files.segmentation_file.visible = False
            get_files.segment_with_epyseg.visible = False
        advanced_visibility()

    def advanced_visibility():
        """ Handle the visibility of the advanced parameters """
        get_files.output_dirname.visible = get_files.advanced_parameters.value
        get_files.show_other_chanels.visible = get_files.advanced_parameters.value
        get_files.process_frames_parallel.visible = get_files.advanced_parameters.value
        get_files.nbparallel_threads.visible = get_files.advanced_parameters.value
        get_files.junction_half_thickness.visible = get_files.advanced_parameters.value
        get_files.verbose_level.visible = get_files.advanced_parameters.value
        get_files.allow_gaps.visible = get_files.advanced_parameters.value
        get_files.show_scale_bar.visible = get_files.advanced_parameters.value
        get_files.epithelial_cells.visible = get_files.advanced_parameters.value

    def load_movie_from_layers(movie, movie_path, segmented):
        """ Load and display the selected layers """
        start_time = ut.start_time()
        nonlocal caxis, cval
        caxis, cval = Epic.movie_from_layer(movie, movie_path)
        imgdir = ut.get_directory(movie_path)
        
        if segmented is None:
            get_files.segmentation_file.visible = True
            get_files.segmentation_file.value = pathlib.Path(imgdir)
            get_files.segment_with_epyseg.visible = True
        
        labname = Epic.suggest_segfile( get_files.output_dirname.value )
        Epic.set_names( get_files.output_dirname.value )
        if labname is not None:
            get_files.segmentation_file.value = pathlib.Path(labname)
            Epic.read_epicure_metadata()    
        if caxis is not None:
            get_files.junction_chanel.max = cval-1
            get_files.junction_chanel.visible = True
            set_chanel()
        show_metatdata(show=True)
        get_files.allow_gaps.value = bool(Epic.epi_metadata["Allow gaps"])
        get_files.verbose_level.value = int(Epic.epi_metadata["Verbose"])
        get_files.call_button.enabled = True
        if "MainChannel" in Epic.epi_metadata:
            get_files.junction_chanel.value = int(Epic.epi_metadata["MainChannel"])

    def show_metatdata(show=True):
        """ Show or update the metadata parameters """
        get_files.scale_xy.value = Epic.epi_metadata["ScaleXY"]
        get_files.timeframe.value = Epic.epi_metadata["ScaleT"]
        get_files.unit_xy.value = Epic.epi_metadata["UnitXY"]
        get_files.unit_t.value = Epic.epi_metadata["UnitT"]
        get_files.scale_xy.visible = show 
        get_files.unit_xy.visible = show
        get_files.timeframe.visible = show 
        get_files.unit_t.visible = show 

    def load_movie():
        """ Load and display the selected movie """
        start_time = ut.start_time()
        nonlocal caxis, cval
        image_file = get_files.image_file.value
        caxis, cval = Epic.load_movie(image_file)
        imgdir = ut.get_directory(image_file)
        get_files.segmentation_file.visible = True
        get_files.segmentation_file.value = pathlib.Path(imgdir)
        labname = Epic.suggest_segfile( get_files.output_dirname.value )
        Epic.set_names( get_files.output_dirname.value )
        if labname is not None:
            get_files.segmentation_file.value = pathlib.Path(labname)
            Epic.read_epicure_metadata()    
        if caxis is not None:
            get_files.junction_chanel.max = cval-1
            get_files.junction_chanel.visible = True
            set_chanel()
        show_metatdata(show=True)
        get_files.segment_with_epyseg.visible = True
        get_files.allow_gaps.value = bool(Epic.epi_metadata["Allow gaps"])
        get_files.verbose_level.value = int(Epic.epi_metadata["Verbose"])
        if "MainChannel" in Epic.epi_metadata:
            get_files.junction_chanel.value = int(Epic.epi_metadata["MainChannel"])
        get_files.call_button.enabled = True
        ut.show_duration(start_time, header="Movie loaded in ")

    def show_others():
        """ Display other chanels from the initial movie """
        for ochan in range(cval):
            ut.remove_layer(viewer, "MovieChannel_"+str(ochan))
        if get_files.show_other_chanels.value == True:
            Epic.add_other_chanels(int(get_files.junction_chanel.value), caxis)

    def set_chanel():
        """ Set the correct chanel that contains the junction signal """
        start_time = ut.start_time()
        Epic.set_chanel( int(get_files.junction_chanel.value), caxis )
        show_others()
        ut.show_duration(start_time, header="Movie chanel loaded in ")

    def show_documentation():
        """ Open the online documentation """
        ut.show_documentation_page( "Start-epicure" )

    def launch_napari_epyseg():
        """ Open napari-epyseg plugin to segment the intensity channel movie """
        print("Running EpySeg with default parameters on the movie. To change the settings, use the napari-epyseg plugin outside of EpiCure or EpySeg module directly")
        parameters = {"tile_width":256, "tile_height":256, "overlap_width":32, "overlap_height":32, "model":"epyseg default(v2)", "norm_min":0, "norm_max":1}
        ut.show_progress( viewer, True )
        progress_bar = progress( len(Epic.img) )
        progress_bar.set_description( "Running epyseg on all frames..." )
        progress_bar.update(0)
        try:
            from epicure.appose_epyseg import go_epyseg
            class LogHandler(logging.Handler):
                def emit(self, record):
                    msg = self.format(record)
                    progress_bar.set_description( msg )

            def setup_logger( name="epyseg_seg" ):
                logger = logging.getLogger(name)
                handler = LogHandler()
                formatter = logging.Formatter('[EpiCure] %(message)s')
                handler.setFormatter( formatter )
                logger.addHandler(handler)
                logger.setLevel( logging.INFO )
                return logger

            logger = setup_logger()
            segres = go_epyseg( Epic.img, parameters, progress_bar=None, logger=logger )
            #segres = appose_epyseg.go_epyseg( Epic.img, parameters, progress_bar=progress_bar )
        except Exception as e:
            ut.show_error( "This option requires the plugin napari-epyseg that is missing.\nInstall it and restart" )
            print(e)
            return
        ut.show_progress( viewer, False )
        segname = str(get_files.image_file.value)+"_epyseg.tif"
        ut.writeTif( segres, segname, 1.0, "uint8", what="Epyseg results saved in " )
        get_files.segmentation_file.value = segname
        get_files.segment_with_epyseg.visible = False


    @magicgui(call_button="START CURE",
            junction_chanel={"widget_type": "Slider", "min":0, "max": 0},
            _ = {"widget_type": "Label"},
            scale_xy = {"widget_type": "LiteralEvalLineEdit"},
            timeframe = {"widget_type": "LiteralEvalLineEdit"},
            __ = {"widget_type": "Label"},
            _____ = {"widget_type": "Label"},
            ______ = {"widget_type": "Label"},
            segment_with_epyseg = {"widget_type": "PushButton", "label": "Segment now with EpySeg"},
            ___ = {"widget_type": "Label"},
            junction_half_thickness={"widget_type": "LiteralEvalLineEdit"},
            nbparallel_threads = {"widget_type": "LiteralEvalLineEdit"},
            verbose_level={"widget_type": "Slider", "min":0, "max": 3},
            go_help = {"widget_type": "PushButton", "label": "Help"},
            )
    def get_files( 
                   image_file = pathlib.Path(cdir),
                   junction_chanel = 0,
                   _ = "Image metadata",
                   scale_xy = 1,
                   unit_xy = "um",
                   timeframe = 1,
                   unit_t = "min",
                   __ = "\nSegmentation\n",
                   _____ = "Load segmentation or TrackMateXML/GEFF file",
                   segmentation_file = pathlib.Path(cdir),
                   ______ = "OR\t\t",
                   segment_with_epyseg = False,
                   ___ = "\n",
                   advanced_parameters = False,
                   show_other_chanels = True,
                   show_scale_bar = True,
                   allow_gaps = True,
                   epithelial_cells = True,
                   process_frames_parallel = False,
                   nbparallel_threads = ncpus,
                   junction_half_thickness = 1,
                   output_dirname = "epics",
                   verbose_level = 1,
                   go_help = False,
                   ):

        print("Starting")
        imname, imdir, outdir = ut.extract_names( image_file, output_dirname )
        update_save_history(imdir)
        #ut.remove_widget(viewer, "Start EpiCure (epicure)")
        ut.remove_all_widgets( viewer )
        Epic.process_parallel = process_frames_parallel
        Epic.set_verbose( verbose_level )
        Epic.nparallel = nbparallel_threads
        #Epic.load_segmentation(segmentation_file)
        #Epic.check_shape()
        Epic.set_thickness( junction_half_thickness )
        Epic.set_scales(scale_xy, timeframe, unit_xy, unit_t)
        Epic.set_scalebar( show_scale_bar )
        Epic.set_gaps_option( allow_gaps )
        Epic.set_epithelia( epithelial_cells )
        ## to handle segmentation from layer or from file
        segmentation_input = {"File":segmentation_file} 
        if segmented is not None:
            segmentation_input["Layer"]=segmented

        Epic.go_epicure(outdir, segmentation_input)
    
    set_visibility()
    get_files.call_button.enabled = False
    get_files.segmentation_file.visible = False
    get_files.segment_with_epyseg.visible = False
    get_files.scale_xy.visible = False
    get_files.unit_xy.visible = False
    get_files.timeframe.visible = False
    get_files.unit_t.visible = False
    if movie is not None:
        load_movie_from_layers(movie, movie_path, segmented)
        get_files.image_file.value = movie_path
        show_metatdata(show=True)
        if segmented is not None:
            get_files.call_button.enabled = True
    get_files.junction_chanel.visible = False
    get_files.advanced_parameters.clicked.connect(set_visibility)
    get_files.show_other_chanels.clicked.connect(show_others)
    get_files.image_file.changed.connect(load_movie)
    get_files.junction_chanel.changed.connect(set_chanel)
    get_files.segment_with_epyseg.clicked.connect( launch_napari_epyseg )
    get_files.go_help.clicked.connect( show_documentation )
    return get_files, Epic

