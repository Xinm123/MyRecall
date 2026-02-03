from doctr.models import ocr_predictor

ocr = ocr_predictor(
    pretrained=True,
    # det_arch="db_mobilenet_v3_large",
    # reco_arch="parseq",
    det_arch="db_resnet50",
    reco_arch="parseq",
)


def extract_text_from_image(image):
    result = ocr([image])
    text = ""
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    text += word.value + " "
                text += "\n"
            text += "\n"
    return text
