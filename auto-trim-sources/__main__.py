from waapi import WaapiClient, CannotConnectToWaapiException
from pprint import pprint
import argparse
from scipy.io import wavfile

# Define arguments for the script
parser = argparse.ArgumentParser(description='Automatically trim the sources for specified objects (ID).')
parser.add_argument('ids', metavar='GUID', nargs='*', help='One or many guid of the form {01234567-89ab-cdef-0123-4567890abcde}. The script retrieves the current selected if no GUID specified.')
parser.add_argument('--threshold_begin', const=1, default=-40, type=int, nargs='?', help='Threshold in decibels under which the begin is trimmed.')
parser.add_argument('--threshold_end', const=1, default=-40, type=int, nargs='?', help='Threshold in decibels under which the end is trimmed.')
parser.add_argument('--no_trim_begin', const=1, default=False, type=bool, nargs='?', help='Trim the begin of the sources')
parser.add_argument('--no_trim_end', const=1, default=False, type=bool, nargs='?', help='Trim the end of the sources')
parser.add_argument('--fade_begin', const=1, default=0, type=float, nargs='?', help='Fade duration when trimming begin')
parser.add_argument('--fade_end', const=1, default=0.02, type=float, nargs='?', help='Fade duration when trimming end')

args = parser.parse_args()

# Convert threshold from decibels to linear
threshold_begin = pow( 10, args.threshold_begin * 0.05);
threshold_end = pow( 10, args.threshold_end * 0.05);

convert_sample_functions = {
    "int16" : lambda s : s / 32767,
    "int32" : lambda s : s / 2147483647,
    "float32" : lambda s : s
}

try:

    # Connecting to Waapi using default URL
    with WaapiClient() as client:

        selected = []
        
        # if no ID is passed as argument, use the selected object from the project
        if args.ids is None or len(args.ids) == 0:
            selected  = client.call("ak.wwise.ui.getSelectedObjects")['objects']
        else:
            selected = map(lambda id: {"id": id}, args.ids)

        set_args = {
            "objects": []
        }

        for obj in selected:

            # Use WAQL to obtain all audio sources under the object
            call_args = { "waql": f"$ \"{obj['id']}\" select this, descendants where type = \"AudioFileSource\""}
            options = { "return": ["originalWavFilePath", "type", "id"]}

            sources = client.call("ak.wwise.core.object.get", call_args, options=options)

            for source in sources['return']:

                # Open the WAV file
                sample_rate, data = wavfile.read(source['originalWavFilePath'])
                print(f"Processing {source['originalWavFilePath']}...")

                duration = data.shape[0] / sample_rate
                trim_end_pos = data.size-1
                trim_begin_pos = 0

                convert_sample = convert_sample_functions[data.dtype.name]
                last_zero_crossing = 0
                last_value = 0

                # Look the PCM data, and find a trim begin
                for i in range(0, data.size-1):
                    value = convert_sample(data[i])

                    # Store zero crossing
                    if (value > 0 and last_value <= 0) or (value < 0 and last_value >= 0):
                        last_zero_crossing = i

                    # Detect threshold
                    if abs(value) > threshold_begin:
                        trim_begin_pos = last_zero_crossing
                        break;

                    last_value = value

                # Find the trim end
                last_zero_crossing = data.size-1
                last_value = 0

                for i in range(data.size-1, trim_begin_pos, -1):
                    value = convert_sample(data[i])

                    # Store zero crossing
                    if (value > 0 and last_value <= 0) or (value < 0 and last_value >= 0):
                        last_zero_crossing = i

                    if abs(value) > threshold_end:
                        trim_end_pos = last_zero_crossing
                        break;

                    last_value = value

                # Set the trim and fade properties on the source object
                set_object = { "object":source['id'] }
                if (not args.no_trim_begin) and trim_begin_pos > 0:
                    set_object["@TrimBegin"] = trim_begin_pos / sample_rate
                if (not args.no_trim_end) and trim_end_pos < data.size - 1:
                    set_object["@TrimEnd"] = trim_end_pos / sample_rate

                set_object["@FadeInDuration"] = args.fade_begin
                set_object["@FadeOutDuration"] = args.fade_end

                # Store changes
                set_args["objects"].append(set_object)

        client.call("ak.wwise.core.undo.beginGroup")
        client.call("ak.wwise.core.object.set", set_args)
        client.call("ak.wwise.core.undo.endGroup", { 'displayName': 'Auto Trim Sources'})


except Exception as e:
    print(str(e))