# Expands an archive file into a collection of files.
#
# Author: Just van den Broecke 2021
#
import re
import os.path
from stetl.component import Config
from stetl.filter import Filter
from stetl.util import Util
from stetl.packet import FORMAT

log = Util.get_log('archiveexpander')


class ArchiveExpander(Filter):
    """
    Abstract Base Class.
    Expands an archive file into a collection of files.

    consumes=FORMAT.string, produces=FORMAT.string
    """

    # Start attribute config meta

    @Config(ptype=str, default='temp_dir', required=True)
    def target_dir(self):
        """
        Target directory to write the extracted files to.
        """
        pass

    @Config(ptype=bool, default=False, required=False)
    def remove_input_file(self):
        """
        Delete input archive file when the chain has been completed?
        """
        pass

    @Config(ptype=bool, default=True, required=False)
    def clear_target_dir(self):
        """
        Delete the files from the target directory  when the chain has been completed?
        """
        pass

    # End attribute config meta

    # Constructor
    def __init__(self, configdict, section, consumes, produces):
        Filter.__init__(self, configdict, section, consumes=consumes, produces=produces)
        self.input_archive_file = None

    @staticmethod
    def safe_filename(name):
        return re.sub(r'[^a-zA-Z0-9.]', '_', name)

    def output_path(self, packet):
        if type(packet.data) == str and '%s' in self.target_dir:
            return self.target_dir % self.safe_filename(packet.data)
        return self.target_dir

    def remove_file(self, file_path):
        if os.path.isfile(file_path):
            os.remove(file_path)

    def wipe_dir(self, dir_path):
        if os.path.isdir(dir_path):
            for file_object in os.listdir(dir_path):
                file_object_path = os.path.join(dir_path, file_object)
                if os.path.isdir(file_object_path):
                    self.wipe_dir(file_object_path)
                    os.rmdir(file_object_path)
                    return

                os.remove(file_object_path)

    def expand_archive(self, packet, output_path):
        log.error('Only classes derived from ArchiveExpander can be used!')

    def invoke(self, packet):

        if packet.data is None:
            log.info("Input data is empty")
            return packet

        formatted_output_path = self.output_path(packet)

        # Optionally clear target dir
        self.wipe_dir(formatted_output_path)

        self.input_archive_file = packet.data

        # Let derived class provide archive expansion (.zip, .tar etc)
        self.expand_archive(self.input_archive_file, formatted_output_path)
        if not os.listdir(formatted_output_path):
            log.warn('No expanded files in {}'.format(formatted_output_path))
            packet.data = None
            return packet

        # ASSERT: expanded files in target dir
        file_count = len(os.listdir(formatted_output_path))
        log.info('Expanded {} into {} OK - filecount={}'.format(
            self.input_archive_file, formatted_output_path, file_count))

        # Output the target dir path where expanded files are found
        packet.data = formatted_output_path

        return packet

    def after_chain_invoke(self, packet):
        if self.remove_input_file:
            self.remove_file(self.input_archive_file)

        if self.clear_target_dir:
            self.wipe_dir(self.output_path(packet))

        return True


class ZipArchiveExpander(ArchiveExpander):
    """
    Extracts all files from a ZIP file into the configured  target directory.

    consumes=FORMAT.string, produces=FORMAT.string
    """

    def __init__(self, configdict, section):
        ArchiveExpander.__init__(self, configdict, section, consumes=FORMAT.string, produces=FORMAT.string)

    def expand_archive(self, file_path, output_path):

        import zipfile
        if not file_path.lower().endswith('zip'):
            log.warn('No zipfile passed: {}'.format(file_path))
            return

        zipfile.ZipFile(file_path).extractall(path=output_path)
