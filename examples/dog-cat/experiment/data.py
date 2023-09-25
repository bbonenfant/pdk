from typing import Optional, TypedDict

from pachyderm_sdk import Client
from pachyderm_sdk.api import pfs
from torch.utils.data import MapDataPipe
from torch.utils.data.datapipes.utils.common import StreamWrapper


class PfsData(TypedDict):
    info: pfs.FileInfo
    file: StreamWrapper


class PfsFileDataPipe(MapDataPipe[PfsData]):
    """MapDataPipe implementation for accessing files stored in PFS.

    This indexes the files of a pfs.Commit at initialization and then
      downloads and serves them at time of access (__getitem__).

    If a previous_commit is specified, then this class accesses all _new_
      files added between previous_commit and commit.
    """

    def __init__(
        self,
        client: Client,
        commit: pfs.Commit,
        path="/",
        previous_commit: Optional[pfs.Commit] = None
    ):
        """"""
        self.client = client
        self.root_file = pfs.File(commit=commit, path=path)
        self.previous_commit = previous_commit

        # Collect a list of all files that will be "piped".
        # Notes:
        #   * This may cause memory issues when indexing >1,000,000 files.
        #   * The memory efficiency of this could be improved by only storing the
        #     URI string of the file, at the cost of requiring an additional
        #     InspectFile call to re-retrieve the FileInfo object at time of access.
        #   * We could take this to the extreme and use pagination to have make the
        #     memory footprint negligible, at the cost of (on average) many network
        #     calls at time of access and making the implementation of this class
        #     significantly more complicated.
        self._file_infos = []
        if previous_commit is not None:
            previous_root_file = pfs.File(commit=self.previous_commit, path=path)
            for diff in self.client.pfs.diff_file(
                    new_file=self.root_file, old_file=previous_root_file
            ):
                if diff.new_file.file_type == pfs.FileType.FILE:
                    self._file_infos.append(diff.new_file)
        else:
            for info in self.client.pfs.walk_file(file=self.root_file):
                if info.file_type == pfs.FileType.FILE:
                    self._file_infos.append(info)

    def __getitem__(self, idx) -> PfsData:
        info = self._file_infos[idx]
        file = self.client.pfs.pfs_file(file=info.file)
        return PfsData(info=info, file=StreamWrapper(file))

    def __len__(self):
        return len(self._file_infos)
