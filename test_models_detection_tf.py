import numpy as np
import pytest
import tensorflow as tf

from doctr.io import DocumentFile
from doctr.models import detection
from doctr.models.detection._utils import dilate, erode
from doctr.models.detection.predictor import DetectionPredictor
from doctr.models.preprocessor import PreProcessor


@pytest.mark.parametrize(
    "arch_name, input_shape, output_size, out_prob",
    [
        ["db_resnet50", (512, 512, 3), (512, 512, 1), True],
        ["db_mobilenet_v3_large", (512, 512, 3), (512, 512, 1), True],
        ["linknet_resnet18", (512, 512, 3), (512, 512, 1), False],
        ["linknet_resnet34", (512, 512, 3), (512, 512, 1), False],
        ["linknet_resnet50", (512, 512, 3), (512, 512, 1), False],
    ],
)
def test_detection_models(arch_name, input_shape, output_size, out_prob):
    batch_size = 2
    tf.keras.backend.clear_session()
    model = detection.__dict__[arch_name](pretrained=True, input_shape=input_shape)
    assert isinstance(model, tf.keras.Model)
    input_tensor = tf.random.uniform(shape=[batch_size, *input_shape], minval=0, maxval=1)
    target = [
        np.array([[.5, .5, 1, 1], [0.5, 0.5, .8, .8]], dtype=np.float32),
        np.array([[.5, .5, 1, 1], [0.5, 0.5, .8, .9]], dtype=np.float32),
    ]
    # test training model
    out = model(input_tensor, target, return_model_output=True, return_preds=True, training=True)
    assert isinstance(out, dict)
    assert len(out) == 3
    # Check proba map
    assert isinstance(out['out_map'], tf.Tensor)
    assert out['out_map'].dtype == tf.float32
    seg_map = out['out_map'].numpy()
    assert seg_map.shape == (batch_size, *output_size)
    if out_prob:
        assert np.all(np.logical_and(seg_map >= 0, seg_map <= 1))
    # Check boxes
    for boxes in out['preds']:
        assert boxes.shape[1] == 5
        assert np.all(boxes[:, :2] < boxes[:, 2:4])
        assert np.all(boxes[:, :4] >= 0) and np.all(boxes[:, :4] <= 1)
    # Check loss
    assert isinstance(out['loss'], tf.Tensor)
    # Target checks
    target = [
        np.array([[0, 0, 1, 1]], dtype=np.uint8),
        np.array([[0, 0, 1, 1]], dtype=np.uint8),
    ]
    with pytest.raises(AssertionError):
        out = model(input_tensor, target, training=True)

    target = [
        np.array([[0, 0, 1.5, 1.5]], dtype=np.float32),
        np.array([[-.2, -.3, 1, 1]], dtype=np.float32),
    ]
    with pytest.raises(ValueError):
        out = model(input_tensor, target, training=True)

    # Check the rotated case
    target = [
        np.array([[.75, .75, .5, .5, 0], [.65, .65, .3, .3, 0]], dtype=np.float32),
        np.array([[.75, .75, .5, .5, 0], [.65, .7, .3, .4, 0]], dtype=np.float32),
    ]
    loss = model(input_tensor, target, training=True)['loss']
    assert isinstance(loss, tf.Tensor) and ((loss - out['loss']) / loss).numpy() < 21e-2


@pytest.fixture(scope="session")
def test_detectionpredictor(mock_pdf):  # noqa: F811

    batch_size = 4
    predictor = DetectionPredictor(
        PreProcessor(output_size=(512, 512), batch_size=batch_size),
        detection.db_resnet50(input_shape=(512, 512, 3))
    )

    pages = DocumentFile.from_pdf(mock_pdf).as_images()
    out = predictor(pages)
    # The input PDF has 2 pages
    assert len(out) == 2

    # Dimension check
    with pytest.raises(ValueError):
        input_page = (255 * np.random.rand(1, 256, 512, 3)).astype(np.uint8)
        _ = predictor([input_page])

    return predictor


@pytest.fixture(scope="session")
def test_rotated_detectionpredictor(mock_pdf):  # noqa: F811

    batch_size = 4
    predictor = DetectionPredictor(
        PreProcessor(output_size=(512, 512), batch_size=batch_size),
        detection.db_resnet50(assume_straight_pages=False, input_shape=(512, 512, 3))
    )

    pages = DocumentFile.from_pdf(mock_pdf).as_images()
    out = predictor(pages)

    # The input PDF has 2 pages
    assert len(out) == 2

    # Dimension check
    with pytest.raises(ValueError):
        input_page = (255 * np.random.rand(1, 256, 512, 3)).astype(np.uint8)
        _ = predictor([input_page])

    return predictor


@pytest.mark.parametrize(
    "arch_name",
    [
        "db_resnet50",
        "db_mobilenet_v3_large",
        "linknet_resnet18",
    ],
)
def test_detection_zoo(arch_name):
    # Model
    tf.keras.backend.clear_session()
    predictor = detection.zoo.detection_predictor(arch_name, pretrained=False)
    # object check
    assert isinstance(predictor, DetectionPredictor)
    input_tensor = tf.random.uniform(shape=[2, 1024, 1024, 3], minval=0, maxval=1)
    out = predictor(input_tensor)
    assert all(isinstance(boxes, np.ndarray) and boxes.shape[1] == 5 for boxes in out)


def test_detection_zoo_error():
    with pytest.raises(ValueError):
        _ = detection.zoo.detection_predictor("my_fancy_model", pretrained=False)


def test_erode():
    x = np.zeros((1, 3, 3, 1), dtype=np.float32)
    x[:, 1, 1] = 1
    x = tf.convert_to_tensor(x)
    expected = tf.zeros((1, 3, 3, 1))
    out = erode(x, 3)
    assert tf.math.reduce_all(out == expected)


def test_dilate():
    x = np.zeros((1, 3, 3, 1), dtype=np.float32)
    x[:, 1, 1] = 1
    x = tf.convert_to_tensor(x)
    expected = tf.ones((1, 3, 3, 1))
    out = dilate(x, 3)
    assert tf.math.reduce_all(out == expected)
