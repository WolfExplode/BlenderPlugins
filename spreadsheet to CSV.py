# credits goes to https://blender.stackexchange.com/questions/293496/how-to-export-blender-spreadsheet-data-into-csv-file-without-applying-gn
import bpy
import csv
import os

m = bpy.context.object.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()

# Get the path to the current Blender file
blend_file_path = bpy.data.filepath

# Get the directory of the Blender file
blend_dir = os.path.dirname(blend_file_path)

# Construct the absolute path to the "data.csv" file
data_file_path = os.path.join(blend_dir, "data.csv")


def append_to_csv(filepath, x, y, z):
    # Check if the file exists
    file_exists = os.path.isfile(filepath)

    # Open the file in append mode
    with open(filepath, 'a', newline='') as file:
        writer = csv.writer(file)

        # If the file doesn't exist, write the header
        if not file_exists:
            writer.writerow(['x', 'y', 'z'])

        # Write the values to the file
        writer.writerow([x, y, z])
        

for i in range(0, len(m.vertices)):
    v = m.vertices[i].co
    append_to_csv(data_file_path,v[0],v[1],v[2])
