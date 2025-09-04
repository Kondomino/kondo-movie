import os
from pathlib import Path
from rich import print

from logger import logger
from movie_maker.effects import Effects

def main():
    try:
        image_folder = 'playground/samples/images/set1'
        for filename in os.listdir(image_folder):
            file_path = Path(os.path.join(image_folder, filename))
            img = Effects.load_image_from_path(image_path=file_path)
            orientation = Effects.get_image_orientation(image_path=file_path)
            print(f"{file_path} : {img.size}, {orientation}")
    except Exception as e:
        logger.exception(e)

if __name__ == '__main__':
    main()