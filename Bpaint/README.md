# Bpaint

Bbrush-style modifier brushes for Texture Paint (Blender 5.1+).

## Brushes it adds

The first time you enter Texture Paint, Bpaint saves two brushes to the asset library your brushes are saved to (the first library with brushes in `Saved/Brushes`, else the User Library): **Bpaint Mask** and **Bpaint Average**. They are saved the same way as **Duplicate Asset**, so you can change them and use **Save Changes to Asset**. Deleting one makes Bpaint save a fresh copy the next time you enter Texture Paint.

## Shift: secondary brush (Blur by default)

- **Shift+LMB** or **Shift+wheel** switches to the secondary brush. Pressing Shift alone does not switch, so other Shift shortcuts keep working.
- **Shift+wheel** resizes the secondary brush (10% per notch) instead of panning the view.
- Releasing **Shift** restores the previous brush.
- To change the secondary brush, start a stroke or scroll with Shift held, then click another brush in the asset shelf while still holding Shift. It is remembered for the session.

## Ctrl: Mask brush

- Pressing **Ctrl** switches to the **Bpaint Mask** brush (Blender's Mask at full strength) immediately. Releasing it restores the previous brush.
- **Ctrl+wheel** resizes the Mask brush.
- Starting a Ctrl+LMB stroke creates a `Bpaint Mask` stencil image (matching the canvas, including UDIM tiles) if none is set, and enables **Stencil Mask**. The Mask brush needs it to work.
- **Alt+LMB** paints the inverted stroke. Blender's default of Ctrl+LMB for inversion is remapped so it doesn't invert the Mask brush.

## Bpaint Average brush

- **Bpaint Average** is a copy of Paint Soft. Pick it from the asset shelf like any other brush.
- When each stroke starts, its color is set to the average of the image under the brush circle (alpha-weighted, averaged in linear color), and the stroke then paints that color. Repeated strokes blend an area towards its mean.
- Only the surface you can see under the circle is sampled, so other UV islands and empty texture space never get into the average. Hidden faces are ignored, and it samples whatever is visible behind them.
- The color is sampled once per stroke, not continuously while dragging.

## World Size

Blender's Scene radius only exists in Sculpt and Grease Pencil. **World Size** does the same for Texture Paint (it replaces the separate World-Space Brush add-on, which should be disabled).

- Turn it on with the **World Size** toggle under Brush Settings (Tool tab). The icon next to it shows a debug overlay with the numbers.
- Each brush's pixel size is rescaled while you zoom, so its size on the surface stays constant. The size is measured at the depth of the 3D cursor.
- Every stroke first moves the 3D cursor to the surface under the mouse, so the depth follows where you paint and the stroke starts at the right size.
- Every brush keeps its own world size, so switching brushes (including the Shift/Ctrl brushes) doesn't change another brush's size. Resizing a brush, with F, the slider or Shift/Ctrl+wheel, sets its new world size. With **Unified Size** on, all brushes share one.
- The toggle is saved per scene, and it resumes when a file saved with it on is opened.

## Known limitations

- **Bpaint Average** doesn't sample UDIM images, and only works in the 3D viewport.

- **The mask only shows in Solid viewport shading.** In Material Preview and Rendered modes the stencil mask is not drawn, so the mask is still there and still limits painting, but you can't see it. Switch to Solid to see and check what you have masked.
