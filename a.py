import banana_dev as banana
import base64
from io import BytesIO
from PIL import Image
from configparser import ConfigParser

model_inputs = {
	"prompt": "a lavalantula (spider made of lava) drifting through the desert inside a rubber tire looking for a time machine",
	"num_inference_steps":50,
	"guidance_scale":9,
	"height":512,
	"width":512,
	"seed":6669
}

config = ConfigParser()
config.read('.env')

# Run the model
out = banana.run(config['DEFAULT']['api_key'] , config['DEFAULT']['model_key'], model_inputs)

# Extract the image and save to output.jpg
image_byte_string = out["modelOutputs"][0]["image_base64"]
image_encoded = image_byte_string.encode('utf-8')
image_bytes = BytesIO(base64.b64decode(image_encoded))
image = Image.open(image_bytes)
image.save("output.jpg")

for currSeed in range(1000, 1300):
    model_inputs['seed'] = currSeed

    out = banana.run(config['DEFAULT']['api_key'] , config['DEFAULT']['model_key'], model_inputs)

    # Extract the image and save to output.jpg
    image_byte_string = out["modelOutputs"][0]["image_base64"]
    image_encoded = image_byte_string.encode('utf-8')
    image_bytes = BytesIO(base64.b64decode(image_encoded))
    image = Image.open(image_bytes)
    image.save(f"tempout/output{currSeed}.jpg")
