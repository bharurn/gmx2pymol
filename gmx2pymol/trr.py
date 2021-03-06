# adapted from https://github.com/andersle/pytrr

import struct
import numpy as np
import os.path

GROMACS_MAGIC = 1993
DIM = 3
TRR_VERSION = 'GMX_trn_file'
TRR_VERSION_B = b'GMX_trn_file'
SIZE_FLOAT = struct.calcsize('f')
SIZE_DOUBLE = struct.calcsize('d')
HEAD_FMT = '{}13i'
HEAD_ITEMS = ('ir_size', 'e_size', 'box_size', 'vir_size', 'pres_size',
              'top_size', 'sym_size', 'x_size', 'v_size', 'f_size',
              'natoms', 'step', 'nre', 'time', 'lambda')
DATA_ITEMS = ('box_size', 'vir_size', 'pres_size',
              'x_size', 'v_size', 'f_size')

class TRRReader():
    def __init__(self, filename):
        self._filename = filename
        self.__fileh = open(filename, 'rb')
        self.__header = None
        
        self.__get_nframes(os.path.getsize(filename))
        
    def close(self):
        if hasattr(self, '__fileh'):
             self.__fileh.close()
        
    def __del__(self):
        self.close()

    def read_frame(self, read_data=True, frame=None):
        """Read a new frame from the file.
        Parameters
        ---------
        read_data : boolean
            If False, we will not read the data, just the header and
            skip forward to the next header position.
        """
        if frame is not None:
            self.__fileh.seek(self._frame_size*frame)
            
        self.__header = self.__read_trr_header()
        if read_data:
            data = self.__read_trr_data()
        else:
            self.__skip_trr_data()
            data = {}
        
        return self.__header, data
    
    def __get_nframes(self, tot_size):
        self.read_frame()
        self._frame_size = self.__fileh.tell()
        nframes = tot_size/self._frame_size
        
        if not nframes.is_integer():
            self.nframes = None
            raise Exception("Frames are not equally sized")
           
        self.nframes = int(nframes)-1
    
    def __read_trr_data(self):
        """Read box, coordinates etc. from a TRR file.
        Parameters
        ----------
        header : dict
            The header read from the file.
        Returns
        -------
        data : dict
            The data we read from the file. It may contain the following
            keys if the data was found in the frame:
            - ``box`` : the box matrix,
            - ``vir`` : the virial matrix,
            - ``pres`` : the pressure matrix,
            - ``x`` : the coordinates,
            - ``v`` : the velocities, and
            - ``f`` : the forces
        """
        data = {}
        
        for key in ('box', 'vir', 'pres'):
            header_key = '{}_size'.format(key)
            if self.__header[header_key] != 0:
                data[key] = self.__read_matrix()
        for key in ('x', 'v', 'f'):
            header_key = '{}_size'.format(key)
            if self.__header[header_key] != 0:
                data[key] = self.__read_coord()
        return data
    
    def __read_coord(self):
        """Read a coordinate section from the TRR file.
        This method will read the full coordinate section from a TRR 
        file. The coordinate section may be positions, velocities or
        forces.
        Parameters
        ----------
        endian : string
            Determines the byte order.
        double : boolean
            If true, we will assume that the numbers
            were stored in double precision.
        natoms : int
            The number of atoms we have stored coordinates for.
        Returns
        -------
        mat : numpy.array
            The coordinates as a numpy array. It will have
            ``natoms`` rows and ``DIM`` columns.
        """
        endian = self.__header['endian']
        double = self.__header['double']
        natoms = self.__header['natoms']
        if double:
            fmt = '{}{}d'.format(endian, natoms * DIM)
        else:
            fmt = '{}{}f'.format(endian, natoms * DIM)
        read = self.__read_struct_buff(fmt)
        mat = np.array(read)
        mat.shape = (natoms, DIM)
        return mat
    
    def __read_matrix(self):
        """Read a matrix from the TRR file.
        Here, we assume that the matrix will be of
        dimensions (DIM, DIM).
        Parameters
        ----------
        endian : string
            Determines the byte order.
        double : boolean
            If true, we will assume that the numbers
            were stored in double precision.
        Returns
        -------
        mat : numpy.array
            The matrix as an numpy array.
        """
        endian = self.__header['endian']
        double = self.__header['double']
        if double:
            fmt = '{}{}d'.format(endian, DIM*DIM)
        else:
            fmt = '{}{}f'.format(endian, DIM*DIM)
        read = self.__read_struct_buff(fmt)
        mat = np.zeros((DIM, DIM))
        for i in range(DIM):
            for j in range(DIM):
                mat[i, j] = read[i*DIM + j]
        return mat
    
    def __read_struct_buff(self, fmt):
        """Unpack from a filehandle with a given format.
        Parameters
        ----------
        fileh : file object
            The file handle to unpack from.
        fmt : string
            The format to use for unpacking.
        Returns
        -------
        out : tuple
            The unpacked elements according to the given format.
        Raises
        ------
        EOFError
            We will raise an EOFError if `fileh.read()` attempts to read
            past the end of the file.
        """
        buff = self.__fileh.read(struct.calcsize(fmt))
        if not buff:
            raise EOFError
        else:
            return struct.unpack(fmt, buff)
    
    def __skip_trr_data(self):
        """Skip coordinates/box data etc.
        This method is used when we want to skip a data section in
        the TRR file. Rather than reading the data it will use the
        sized read in the header to skip ahead to the next frame.
        Parameters
        ----------
        header : dict
            The header read from the TRR file.
        """
        offset = sum([self.__header[key] for key in DATA_ITEMS])
        self.__fileh.seek(offset, 1)
        return None
    
    def __read_trr_header(self):
        """Read a header from a TRR file.
        Parameters
        ----------
        fileh : file object
            The file handle for the file we are reading.
        Returns
        -------
        header : dict
            The header read from the file.
        """
        endian = '>'

        magic = self.__read_struct_buff('{}1i'.format(endian))[0]

        if magic == GROMACS_MAGIC:
            pass
        else:
            magic = TRRReader.__swap_integer(magic)
            endian = TRRReader.__swap_endian(endian)

        slen = self.__read_struct_buff('{}2i'.format(endian))
        raw = self.__read_struct_buff('{}{}s'.format(endian, slen[0]-1))
        version = raw[0].split(b'\0', 1)[0].decode('utf-8')
        if not version == TRR_VERSION:
            raise ValueError('Unknown format')

        head_fmt = HEAD_FMT.format(endian)
        head_s = self.__read_struct_buff(head_fmt)
        header = {}
        for i, val in enumerate(head_s):
            key = HEAD_ITEMS[i]
            header[key] = val
        # The next are either floats or double
        double = self.__is_double(header)
        if double:
            fmt = '{}2d'.format(endian)
        else:
            fmt = '{}2f'.format(endian)
        header_r = self.__read_struct_buff(fmt)
        header['time'] = header_r[0]
        header['lambda'] = header_r[1]
        header['endian'] = endian
        header['double'] = double
        return header
    
    @staticmethod
    def __is_double(header):
        """Determines we we should use double precision.
        This method determined the precision to use when reading
        the TRR file. This is based on the header read for a given
        frame which defines the sizes of certain "fields" like the box
        or the positions. From this size, the precision can be obtained.
        Parameters
        ----------
        header : dict
            The header read from the TRR file.
        Returns
        -------
        out : boolean
            True if we should use double precision.
        """
        key_order = ('box_size', 'x_size', 'v_size', 'f_size')
        size = 0
        for key in key_order:
            if header[key] != 0:
                if key == 'box_size':
                    size = int(header[key] / DIM**2)
                    break
                else:
                    size = int(header[key] / (header['natoms'] * DIM))
                    break
        if (size != SIZE_FLOAT) and (size != SIZE_DOUBLE):
            raise ValueError('Could not determine size!')
        else:
            return size == SIZE_DOUBLE
    
    @staticmethod
    def __swap_integer(integer):
        """Convert little/big endian."""
        return (((integer << 24) & 0xff000000) | ((integer << 8) & 0x00ff0000) |
                ((integer >> 8) & 0x0000ff00) | ((integer >> 24) & 0x000000ff))

    @staticmethod
    def __swap_endian(endian):
        """Just swap the string for selecting big/little."""
        if endian == '>':
            return '<'
        elif endian == '<':
            return '>'
        else:
            raise ValueError('Undefined swap!')

def read_trr(file, frame):
    return TRRReader(file).read_frame(frame=frame)

def get_trr_frames(file):
    return TRRReader(file).nframes

def check_trr(file):
    trr = TRRReader(file)
    data = trr.read_frame()
    if 'x' not in data:
        raise KeyError("Position data not present in TRR file")
    elif 'box' not in data:
        raise KeyError("Box data not present in TRR file")
    if 'f' not in data:
        raise KeyError("Force data not present in TRR file")
        
def _write_trr_header(outfile, header, floatfmt, endian=None):
    """Helper method for writing a header to a TRR file.
    Parameters
    ----------
    outfile : filehandle
        The file we can write to.
    header : dict
        The header data for the TRR file.
    floatfmt : string
        The string which gives the format for floats. It should indicate
        if we are writing for double or single precision.
    endian : string, optional
        Can be used to force endianess.
    """
    slen = (13, 12)
    fmt = ['1i', '2i', '{}s'.format(slen[0] - 1), '13i']
    if endian:
        fmt = [endian + i for i in fmt]
    outfile.write(struct.pack(fmt[0], GROMACS_MAGIC))
    outfile.write(struct.pack(fmt[1], *slen))
    outfile.write(struct.pack(fmt[2], TRR_VERSION_B))
    head = [header[key] for key in HEAD_ITEMS[:13]]
    outfile.write(struct.pack(fmt[3], *head))
    outfile.write(struct.pack(floatfmt.format(1), header['time']))
    outfile.write(struct.pack(floatfmt.format(1), header['lambda']))


def write_trr(filename, data, endian=None, double=False, append=False):
    """Write data in TRR format to a file.
    Parameters
    ----------
    filename : string
        The file we will write to.
    data : dict
        The data we will write to the file.
    endian : string, optional
        Select the byte order; big-endian or little-endian. If not
        specified, the native byte order will be used.
    double : boolean, optional
        If True, we will write in double precision.
    append : boolean, optional
        If True, we will append to the given file.
    """
    if double:
        size = SIZE_DOUBLE
        floatfmt = '{}d'
    else:
        size = SIZE_FLOAT
        floatfmt = '{}f'
    if endian:
        floatfmt = endian + floatfmt

    header = {}
    for key in HEAD_ITEMS:
        header[key] = 0

    header['natoms'] = data['natoms']
    header['step'] = data['step']
    header['box_size'] = size * DIM * DIM
    for i in ('x', 'v', 'f'):
        if i in data:
            header['{}_size'.format(i)] = data['natoms'] * size * DIM
    header['endian'] = endian
    header['double'] = double
    header['time'] = data['time']
    header['lambda'] = data['lambda']

    if append:
        mode = 'ab'
    else:
        mode = 'wb'
    with open(filename, mode) as outfile:
        _write_trr_header(outfile, header, floatfmt, endian=endian)
        for key in DATA_ITEMS:
            if header[key] != 0:
                # Note: We assume that the data is a numpy array, and that
                # we can find it as data['x'], data['v'], ... and so on.
                matrix = data[key.split('_')[0]]
                fmt = floatfmt.format(matrix.size)
                outfile.write(struct.pack(fmt, *matrix.flatten()))
    return header