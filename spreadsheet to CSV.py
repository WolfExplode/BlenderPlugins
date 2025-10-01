import bpy
import csv
import os

obj = bpy.context.object

# Check if an object is selected and that it's a mesh type
if not obj or obj.type != 'MESH':
    print("Error: No mesh object selected.")
    # You might want to raise an exception or exit the script here
else:
    # Get the mesh data from the evaluated object
    m = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()

    # --- File Path Construction ---
    # Get the name of the selected object, replacing spaces with underscores for a clean filename
    object_name = obj.name.replace(" ", "_")
    
    # Construct the CSV filename using the object's name
    csv_filename = f"{object_name}.csv"

    # Get the path to the current Blender file
    blend_file_path = bpy.data.filepath

    # Get the directory of the Blender file
    blend_dir = os.path.dirname(blend_file_path)

    # Construct the absolute path to the CSV file
    data_file_path = os.path.join(blend_dir, csv_filename)


    # --- CSV Writer Function ---
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
            

    # --- Main Export Loop ---
    print(f"Exporting vertices of '{obj.name}' to: {data_file_path}")

    for i in range(0, len(m.vertices)):
        v = m.vertices[i].co
        
        # Format the coordinates to exactly 3 decimal places
        x_formatted = float("{:.3f}".format(v[0]))
        y_formatted = float("{:.3f}".format(v[1]))
        z_formatted = float("{:.3f}".format(v[2]))
        
        append_to_csv(data_file_path, x_formatted, y_formatted, z_formatted)
        
    # Free the temporary mesh data (good practice in Blender scripting)
    obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
