# Extracts a file from and archive file like a .zip,
# and saves it as the given file name.
#
# Author: Just van den Broecke (generic and VsiFileExtractor)
# Author: Frank Steggink (ZipFileExtractor)
# Author: Ynte de Wolff (Dynamic output path)
#
import re
import os.path
from stetl.component import Config
from stetl.filter import Filter
from stetl.util import Util
from stetl.packet import FORMAT

log = Util.get_log('fileextractor')

DEFAULT_BUFFER_SIZE = 1024 * 1024 * 1024


class FileExtractor(Filter):
    """
    Abstract Base Class.
    Extracts a file an archive and saves as the configured file name.

    consumes=FORMAT.any, produces=FORMAT.string
    """

    # Start attribute config meta

    @Config(ptype=str, default=None, required=True)
    def file_path(self):
        """
        File name to write the extracted file to.
        """
        pass

    @Config(ptype=bool, default=True, required=False)
    def delete_file(self):
        """
        Delete the file when the chain has been completed?
        """
        pass

    @Config(ptype=int, default=DEFAULT_BUFFER_SIZE, required=False)
    def buffer_size(self):
        """
        Buffer size for read buffer during extraction.
        """
        pass

    # End attribute config meta

    # Constructor
    def __init__(self, configdict, section, consumes=FORMAT.any, produces=FORMAT.string):
        Filter.__init__(self, configdict, section, consumes=consumes, produces=produces)

    @staticmethod
    def safe_filename(name):
        return re.sub(r'[^a-zA-Z0-9.]', '_', name)

    def output_path(self, _packet):
        return self.file_path

    def delete_target_file(self, packet):
        if os.path.isfile(self.output_path(packet)):
            os.remove(self.output_path(packet))

    def extract_file(self, packet):
        log.error('Only classes derived from FileExtractor can be used!')

    def invoke(self, packet):

        if packet.data is None:
            log.info("Input data is empty")
            return packet

        # Optionally remove old file
        self.delete_target_file(packet)
        self.extract_file(packet)
        packet.data = self.output_path(packet)

        if not os.path.isfile(packet.data):
            log.warn('Extracted file {} does not exist'.format(packet.data))
            packet.data = None

        return packet

    def after_chain_invoke(self, packet):
        if not self.delete_file:
            return

        # This does not work with a dynamic output path because packet is None!
        # We cannot reconstruct the output path
        self.delete_target_file(packet)

        return True


class ZipFileExtractor(FileExtractor):
    """
    Extracts a file from a ZIP file, and saves it as the given file name.
    Author: Frank Steggink

    consumes=FORMAT.record, produces=FORMAT.string
    """

    def __init__(self, configdict, section):
        FileExtractor.__init__(self, configdict, section, consumes=FORMAT.record)

    def output_path(self, packet):
        if type(packet.data) == dict and '%s' in self.file_path:
            # typeof packet.data = Dict{name: string, file_path: string}
            return self.file_path % self.safe_filename(packet.data['name'])
        else:
            return self.file_path

    def extract_file(self, packet):

        import zipfile

        with zipfile.ZipFile(packet.data['file_path']) as z:
            with open(self.output_path(packet), 'wb') as f:
                with z.open(packet.data['name']) as zf:
                    while True:
                        buffer = zf.read(self.buffer_size)
                        if not buffer:
                            break
                        f.write(buffer)


class VsiFileExtractor(FileExtractor):
    """
    Extracts a file from a GDAL /vsi path spec, and saves it as the given file name.

    Example paths:
    /vsizip/{/project/nlextract/data/BAG-2.0/BAGNLDL-08112020.zip}/9999STA08112020.zip'
    /vsizip/{/vsizip/{BAGGEM0221L-15022021.zip}/GEM-WPL-RELATIE-15022021.zip}/GEM-WPL-RELATIE-15022021-000001.xml

    See also stetl.inputs.fileinput.VsiZipFileInput that generates these paths.

    Author: Just van den Broecke

    consumes=FORMAT.gdal_vsi_path, produces=FORMAT.string
    """

    def __init__(self, configdict, section):
        FileExtractor.__init__(self, configdict, section, consumes=FORMAT.gdal_vsi_path)

    def output_path(self, packet):
        if type(packet.data) == str and '%s' in self.file_path:
            # typeof packet.data = String
            return self.file_path % self.safe_filename(packet.data)
        else:
            return self.file_path

    def extract_file(self, packet):
        from stetl.util import gdal

        # Example input path can be as complex as this:
        #
        vsi_file_path = packet.data
        vsi = None
        vsi_len = 0
        try:
            # gdal.VSIF does not support 'with' so old-school open/close.
            log.info('Extracting {}'.format(vsi_file_path))
            vsi = gdal.VSIFOpenL(vsi_file_path, 'rb')
            with open(self.output_path(packet), 'wb') as f:
                gdal.VSIFSeekL(vsi, 0, 2)
                vsi_len = gdal.VSIFTellL(vsi)
                gdal.VSIFSeekL(vsi, 0, 0)
                read_size = self.buffer_size
                if vsi_len < read_size:
                    read_size = vsi_len

                while True:
                    buffer = gdal.VSIFReadL(1, read_size, vsi)
                    if not buffer or len(buffer) == 0:
                        break
                    f.write(buffer)

        except Exception as e:
            log.error('Cannot extract {} err={}'.format(vsi_file_path, str(e)))
            raise e
        finally:
            if vsi:
                log.info('Extracted {} ok len={} bytes'.format(vsi_file_path, vsi_len))
                gdal.VSIFCloseL(vsi)
