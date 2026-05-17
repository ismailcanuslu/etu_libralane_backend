# KLayout batch: GDS -> PNG (headless)
# Kullanim: klayout -zz -b -r klayout_export_png.rb -rd-input=/work/file.gds -rd-output=/work/out.png

include RBA

input_path = $input || ARGV[0]
output_path = $output || ARGV[1]
width = ($width || 1200).to_i
height = ($height || 900).to_i

raise "input path required" if input_path.nil? || input_path.empty?
raise "output path required" if output_path.nil? || output_path.empty?

layout = RBA::Layout::new
layout.read(input_path)

view = RBA::LayoutView::new
view.show_layout(layout, 0)
view.max_hier
view.save_image(output_path, width, height)
puts "Wrote #{output_path}"
