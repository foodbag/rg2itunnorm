#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import array
import mutagen
import mutagen.id3
import mutagen.mp4

global verbose
verbose = False


def replaygain_init(tags, album=False):
    if isinstance(tags, mutagen.id3.ID3):
        if verbose:
            print "Processing ID3 tags."
        return ReplayGainMP3(tags, album)
    elif isinstance(tags, mutagen.mp4.MP4Tags):
        if verbose:
            print "Processing MP4 metadata."
        return ReplayGainMP4(tags, album)

# See http://svn.slimdevices.com/slim/7.6/trunk/server/Slim/Utils/SoundCheck.pm?view=markup
# for a more detailed description of what is going on here.


class ReplayGainError(ValueError):
    pass


class ReplayGain:
    peak = 0
    gain = 0
    iTunNORM = ['00000000', '00000000', '00000000', '00000000', '00024CA8',
                '00024CA8', '00007FFF', '00007FFF', '00024CA8', '00024CA8']

    def _to_soundcheck(self):
        ret = []
        ret.extend(self.iTunNORM)
        ret[0] = self.__gain_to_sc(1000)
        #if ret[1] != '00000000':
        ret[1] = ret[0]
        ret[2] = self.__gain_to_sc(2500)
        #if ret[3] != '00000000':
        ret[3] = ret[2]

        if verbose:
            print "New iTunNORM: %s" % " ".join(ret)
        return ' %s' % ' '.join(ret)

    def __gain_to_sc(self, base):
        return self.__to_string(min(round((10 ** (-self.gain / 10)) * base), 65534))

    def __peak_to_sc(self):
        # FIXME: Use ReplayGain peak
        return max(self.iTunNORM[6], self.iTunNORM[7])

    def __to_string(self, val):
        return '%08X' % val


class ReplayGainMP3(ReplayGain):
    def __init__(self, tags, album=False):
        #print tags
        #sys.exit(1)
        k = u'TXXX:REPLAYGAIN_TRACK_GAIN'
        if u'TXXX:replaygain_track_gain' in tags:
            k = u'TXXX:replaygain_track_gain'
        k2 = u'TXXX:REPLAYGAIN_TRACK_PEAK'
        if u'TXXX:replaygain_track_peak' in tags:
            k2 = u'TXXX:replaygain_track_peak'
        if album:
            if u'TXXX:REPLAYGAIN_ALBUM_GAIN' in tags:
                k = u'TXXX:REPLAYGAIN_ALBUM_GAIN'
                k2 = u'TXXX:REPLAYGAIN_ALBUM_PEAK'
                if u'TXXX:replaygain_album_peak' in tags:
                    k2 = u'TXXX:replaygain_album_peak'
            elif u'TXXX:replaygain_album_gain' in tags:
                k = u'TXXX:replaygain_album_gain'
                k2 = u'TXXX:REPLAYGAIN_ALBUM_PEAK'
                if u'TXXX:replaygain_album_peak' in tags:
                    k2 = u'TXXX:replaygain_album_peak'
            else:
                print "Warning: Album ReplayGain requested, but no tag was found."
                print "\tContinuing anyway with track ReplayGain instead..."
        #print k
        #print k2
        if k in tags:
            if verbose:
                print "%s" % tags[k]
            setattr(self, "gain", float(tags[k][0].split()[0]))
        else:
            raise ReplayGainError("No RVA2 tag found!")
        if k2 in tags:
            if verbose:
                print "%s" % tags[k2]
            #print float(tags[k2][0])
            setattr(self, "peak", float(tags[k2][0]))
        else:
            raise ReplayGainError("No RVA2 tag found!")
        if u'COMM:iTunNORM:eng' in tags:
            if verbose:
                print "Starting iTunNORM:%s" % tags[u'COMM:iTunNORM:eng'].text[0]
            self.iTunNORM = tags[u'COMM:iTunNORM:eng'].text[0].split()

    def to_soundcheck(self, tags):
        frame = mutagen.id3.COMM(encoding=0, lang=u'eng', desc=u'iTunNORM', text=self._to_soundcheck())
        tags.add(frame)


class ReplayGainMP4(ReplayGain):
    def __init__(self, tags, album=False):
        #print tags
        #sys.exit(1)
        k = "track"
        if album:
            if "----:com.apple.iTunes:replaygain_album_gain" in tags:
                k = "album"
            else:
                print "Warning: Album ReplayGain requested, but no tag was found."
                print "\tContinuing anyway with track ReplayGain instead..."
        for i in ("gain", "peak"):
            if ("----:com.apple.iTunes:replaygain_%s_%s" % (k, i)) in tags:
                # the replaygain tag is a string (e.g. "-3 dB") i.e. a split is needed
                rg_str = tags["----:com.apple.iTunes:replaygain_%s_%s" % (k, i)][0]
                setattr(self, i, float((rg_str.split())[0]))
                if verbose:
                    print "ReplayGain %s: %f" % (i, getattr(self, i))
            elif i == "gain":
                raise ReplayGainError("No ReplayGain gain tag!")

        if "----:com.apple.iTunes:iTunNORM" in tags:
            if verbose:
                print "Starting iTunNORM:%s" % tags["----:com.apple.iTunes:iTunNORM"][0]
            self.iTunNORM = tags["----:com.apple.iTunes:iTunNORM"][0].split()

    def to_soundcheck(self, tags):
        tags["----:com.apple.iTunes:iTunNORM"] = self._to_soundcheck()


def main(argv):
    parser = argparse.ArgumentParser(description='Convert ReplayGain metadata to iTunes SoundCheck.')
    parser.add_argument('infiles', nargs='+', metavar='infile', help='file(s) to process')
    parser.add_argument('-a', '--album', action='store_true', default=False,
                        help='use album ReplayGain instead of track ReplayGain')
    # parser.add_argument('-t', '--timestamp', action='store_true', default=False,
    #                     help='reset modification timestamp after altering file')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='be verbose')

    args = parser.parse_args()

    global verbose
    verbose = args.verbose

    for i, filename in enumerate(args.infiles):
        if verbose:
            print "Processing [%d/%d]: %s" % (i + 1, len(args.infiles), filename)
        else:
            print "Processing [%d/%d]" % (i + 1, len(args.infiles))

        try:
            audio = mutagen.File(filename, options=[mutagen.id3.ID3FileType, mutagen.mp4.MP4])
        except IOError:
            print "Error: Failed to open '%s'" % filename
            continue
        if not audio:
            print "Error: '%s' is neither mp3 or mp4." % filename
            continue
        try:
            rg = replaygain_init(audio.tags, album=args.album)
        except ReplayGainError, err:
            print "Error: %s" % err
            sys.exit(255)

        rg.to_soundcheck(audio.tags)
        #sys.exit(1)

        audio.save()

if __name__ == "__main__":
    main(sys.argv)
