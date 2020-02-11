"""
Collect all the interesting data for analysis
"""
from __future__ import absolute_import
import os
import json
from . import archive
import logging
from itertools import chain
from tempfile import NamedTemporaryFile
from insights import collect

from ..contrib.soscleaner import SOSCleaner
# from .utilities import get_version_info, read_pidfile, get_tags
from .utilities import get_version_info, get_tags
from .constants import InsightsConstants as constants

APP_NAME = constants.app_name
logger = logging.getLogger(__name__)
# python 2.7
SOSCLEANER_LOGGER = logging.getLogger('soscleaner')
SOSCLEANER_LOGGER.setLevel(logging.ERROR)
# python 2.6
SOSCLEANER_LOGGER = logging.getLogger('insights-client.soscleaner')
SOSCLEANER_LOGGER.setLevel(logging.ERROR)


class DataCollector(object):
    '''
    Run commands and collect files
    '''

    def __init__(self, config, archive_=None, mountpoint=None):
        self.config = config
        self.archive = archive_ if archive_ else archive.InsightsArchive(config)
        self.mountpoint = '/'
        if mountpoint:
            self.mountpoint = mountpoint
        self.hostname_path = None

    def _write_branch_info(self, branch_info):
        logger.debug("Writing branch information to archive...")
        self.archive.add_metadata_to_archive(
            json.dumps(branch_info), '/branch_info')

    def _write_display_name(self):
        if self.config.display_name:
            logger.debug("Writing display_name to archive...")
            self.archive.add_metadata_to_archive(
                self.config.display_name, '/display_name')

    def _write_version_info(self):
        logger.debug("Writing version information to archive...")
        version_info = get_version_info()
        self.archive.add_metadata_to_archive(
            json.dumps(version_info), '/version_info')

    def _write_tags(self):
        logger.debug("Writing tags to archive...")
        tags = get_tags()
        if tags is not None:
            def f(k, v):
                if type(v) is list:
                    col = []
                    for val in v:
                        col.append(f(k, val))
                    return list(chain.from_iterable(col))
                elif type(v) is dict:
                    col = []
                    for key, val in v.items():
                        col.append(f(k + ":" + key, val))
                    return list(chain.from_iterable(col))
                else:
                    return [{"key": k, "value": v, "namespace": constants.app_name}]
            t = []
            for k, v in tags.items():
                iv = f(k, v)
                t.append(iv)
            t = list(chain.from_iterable(t))
            self.archive.add_metadata_to_archive(json.dumps(t), '/tags.json')

    def run_collection(self, rm_conf, branch_info):
        '''
        Run specs and collect all the data
        '''
        # parent_pid = read_pidfile()  # TODO: leverage this in core collection
        if rm_conf is None:
            rm_conf = {}
        logger.debug('Beginning to run collection...')

        collected_data_path = collect.collect(tmp_path=self.archive.tmp_dir, rm_conf=rm_conf)

        # update the archive object with the reported data location from Insights Core
        self.archive.update(collected_data_path)
        logger.debug('Collection finished.')

        # collect metadata
        logger.debug('Collecting metadata...')
        self._write_branch_info(branch_info)
        self._write_display_name()
        self._write_version_info()
        self._write_tags()
        logger.debug('Metadata collection finished.')

    def done(self, rm_conf):
        """
        Do finalization stuff
        """
        if self.config.obfuscate:
            cleaner = SOSCleaner(quiet=True)
            clean_opts = CleanOptions(
                self.config, self.archive.tmp_dir, rm_conf)
            fresh = cleaner.clean_report(clean_opts, self.archive.archive_dir)
            if clean_opts.keyword_file is not None:
                os.remove(clean_opts.keyword_file.name)
                logger.warn("WARNING: Skipping keywords found in remove.conf")
            self.archive.tar_file = fresh[0]
            return fresh[0]
        return self.archive.create_tar_file()


class CleanOptions(object):
    """
    Options for soscleaner
    """
    def __init__(self, config, tmp_dir, rm_conf):
        self.report_dir = tmp_dir
        self.domains = []
        self.files = []
        self.quiet = True
        self.keyword_file = None
        self.keywords = None

        if rm_conf:
            try:
                keywords = rm_conf['keywords']
                self.keyword_file = NamedTemporaryFile(delete=False)
                self.keyword_file.write("\n".join(keywords).encode('utf-8'))
                self.keyword_file.flush()
                self.keyword_file.close()
                self.keywords = [self.keyword_file.name]
                logger.debug("Attmpting keyword obfuscation")
            except LookupError:
                pass

        if config.obfuscate_hostname:
            # default to its original location
            self.hostname_path = 'data/insights_commands/hostname'
        else:
            self.hostname_path = None
