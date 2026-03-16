bl_info = {
    "name": "translateShapekeysToEnglish",
    "author": "WolfExplode",
    "version": (1, 0, 0),
    "blender": (3, 2, 0),
    }

import bpy
# Translation lookup table (Japanese to English)
japanese_to_english = {
    "あご": "Chin",
    "ほお": "Cheek",
    "目": "Eye",
    "まゆげ": "Eyebrow",
    "口": "Mouth",
    "はな": "Nose",
    "ひたい": "Forehead",
    "かみ": "Hair",
    "みみ": "Ear",
    "くちびる": "Lips",
    
    "困る": "Worried",
    "困る左": "Worried Left",
    "困る右": "Worried Right",
    "にこり": "Smile",
    "にこり左": "Smile Left",
    "にこり右": "Smile Right",
    "にこり２": "Smile 2",
    "にこり２左": "Smile 2 Left",
    "にこり２右": "Smile 2 Right",
    "怒り": "Angry",
    "怒り左": "Angry Left",
    "怒り右": "Angry Right",
    "上": "Up",
    "上左": "Up Left",
    "上右": "Up Right",
    "下": "Down",
    "下左": "Down Left",
    "下右": "Down Right",
    "平行": "Parallel",
    "平行左": "Parallel Left",
    "平行右": "Parallel Right",
    "入": "In",
    "入左": "In Left",
    "入右": "In Right",
    "まばたき": "Blink",
    "ウィンク２": "Wink 2",
    "ウィンク２右": "Wink 2 Right",
    "笑い": "Laugh",
    "ウィンク": "Wink",
    "ウィンク右": "Wink Right",
    "じと目": "Droopy Eyes",
    "じと目左": "Droopy Eyes Left",
    "じと目右": "Droopy Eyes Right",
    "びっくり": "Surprised",
    "びっくり左": "Surprised Left",
    "びっくり右": "Surprised Right",
    "キリッ": "Determined",
    "キリッ左": "Determined Left",
    "キリッ右": "Determined Right",
    "たれ目": "Droopy",
    "たれ目左": "Droopy Left",
    "たれ目右": "Droopy Right",
    "笑い目": "Smiling Eyes",
    "笑い目左": "Smiling Eyes Left",
    "笑い目右": "Smiling Eyes Right",
    "悲しい目": "Sad Eyes",
    "悲しい目左": "Sad Eyes Left",
    "悲しい目右": "Sad Eyes Right",
    "瞳小": "Pupils Small",
    "瞳小左": "Pupils Small Left",
    "瞳小右": "Pupils Small Right",
    "恐ろしい子！": "Scary",
    "恐ろしい子！左": "Scary Left",
    "恐ろしい子！右": "Scary Right",
    "カメラ目": "Camera Eyes",
    "なんで": "Why",
    "ぺろっ": "Tongue Out",
    "てへぺろ": "Tehepero",
    "口角下げ左": "Mouth Corner Down Left",
    "口角下げ右": "Mouth Corner Down Right",
    "口角上げ左": "Mouth Corner Up Left",
    "口角上げ右": "Mouth Corner Up Right",
    "口横広げ左": "Mouth Stretch Left",
    "口横広げ右": "Mouth Stretch Right",
    "口横広げ2右": "Mouth Stretch 2 Right",
    "口横広げ2左": "Mouth Stretch 2 Left",
    "口上": "Mouth Up",
    "口下": "Mouth Down",
    "口右": "Mouth Right",
    "口左": "Mouth Left",
    "口角前": "Mouth Corner Forward",
    "口横縮小": "Mouth Narrow",
    "齶右": "Jaw Right",
    "齶左": "Jaw Left",
    "齶前": "Jaw Forward",
    "齶上": "Jaw Up",
    "鼻上": "Nose Up",
    "鼻下": "Nose Down",
    "唇中": "Lips Center",
    "星目": "Star Eyes",
    "星目2": "Star Eyes 2",
    "はぁと": "Heart",
    "はぁと2": "Heart 2",
    "汗": "Sweat",
    "はちゅ": "Hachu",
    "惊": "Shock",
    "照れ": "Bashful",
    "照れ2": "Bashful 2",
    "涙": "Tears",
    "基型":"Basis"
}

# Create reverse lookup table (English to Japanese)
english_to_japanese = {v: k for k, v in japanese_to_english.items()}

def translate_shape_keys(translation_dict):
    translated_count = 0
    selected_meshes = 0
    
    if not bpy.context.selected_objects:
        print("No objects selected!")
        return 0
        
    for obj in bpy.context.selected_objects:
        if obj.type != 'MESH':
            print(f"Skipping non-mesh object: {obj.name}")
            continue
            
        if not obj.data.shape_keys:
            print(f"No shape keys found in: {obj.name}")
            continue
            
        selected_meshes += 1
        key_blocks = obj.data.shape_keys.key_blocks
        
        for key_block in key_blocks:
            original_name = key_block.name
            translated_name = translation_dict.get(original_name)
            
            if translated_name:
                print(f"Translating {original_name} -> {translated_name}")
                key_block.name = translated_name
                translated_count += 1
            else:
                print(f"No translation found for: {original_name}")

    print(f"Processed {selected_meshes} mesh(es), translated {translated_count} shape keys")
    return translated_count

class TranslateShapeKeysEnglish(bpy.types.Operator):
    bl_idname = "object.translate_shape_keys_english"
    bl_label = "Translate to English"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = translate_shape_keys(japanese_to_english)
        if count == 0:
            self.report({'WARNING'}, "No translations occurred! Check console for details")
        else:
            self.report({'INFO'}, f"Translated {count} shape keys to English")
        return {'FINISHED'}

class TranslateShapeKeysJapanese(bpy.types.Operator):
    bl_idname = "object.translate_shape_keys_japanese"
    bl_label = "Translate to Japanese"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = translate_shape_keys(english_to_japanese)
        if count == 0:
            self.report({'WARNING'}, "No translations occurred! Check console for details")
        else:
            self.report({'INFO'}, f"Translated {count} shape keys to Japanese")
        return {'FINISHED'}

class VIEW3D_PT_ShapeKeyTranslator(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = "Shape Key Translator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Translate Shape Keys:")
        row = layout.row()
        row.operator("object.translate_shape_keys_english")
        row.operator("object.translate_shape_keys_japanese")

def register():
    bpy.utils.register_class(TranslateShapeKeysEnglish)
    bpy.utils.register_class(TranslateShapeKeysJapanese)
    bpy.utils.register_class(VIEW3D_PT_ShapeKeyTranslator)

def unregister():
    bpy.utils.unregister_class(TranslateShapeKeysEnglish)
    bpy.utils.unregister_class(TranslateShapeKeysJapanese)
    bpy.utils.unregister_class(VIEW3D_PT_ShapeKeyTranslator)

if __name__ == "__main__":
    register()