import altair as alt
import numpy as np
import pandas as pd
import pytest

from io import StringIO

from pandas.testing import assert_frame_equal
from pandas.testing import assert_series_equal
from pandas.testing import assert_index_equal
from numpy.testing import assert_allclose
from numpy.testing import assert_equal

from statsmodels.regression.linear_model import RegressionResultsWrapper

from src.tasks import _column_wrangler
from src.tasks import _obj_wrangler
from src.tasks import _factor_wrangler
from src.tasks import clean_data
from src.tasks import wrangle_na
from src.tasks import run_model
from src.tasks import transform_data
from src.tasks import encode_data
from src.tasks import gelman_standardize_data
from src.tasks import plot_confidence_intervals


# TESTCASES

STR_NA_VALUES = [
    "-1.#IND",
    "1.#QNAN",
    "1.#IND",
    "-1.#QNAN",
    "#N/A N/A",
    "#N/A",
    "N/A",
    "n/a",
    "NA",
    "<NA>",
    "#NA",
    "NULL",
    "null",
    "NaN",
    "-NaN",
    "nan",
    "-nan",
    "",
]  # Strings recognised as NA/NaN by Pandas

STR_DATA_EXAMPLES = {
    # Time series data with integer and binary cols, no range index,
    # and one unnamed col.
    'us_consump_1940s':
        ""","year","income","expenditure","war",
        0,"1940",241,226,0
        1,"1941",280,240,0
        2,"1942",319,235,1
        3,"1943",331,245,1
        4,"1944",345,255,1
        5,"1945",340,265,1
        6,"1946",332,295,0
        7,"1947",320,300,0
        8,"1948",339,305,0
        9,"1949",338,315,0""",
    # Cross-sectional data with float, string, factor, binary, and boolean cols
    'iraq_vote':
        ""","y","state.abb","name","rep","state.name","gorevote"
        0,1,"AL","SESSIONS (R AL)",TRUE,"Alabama",41.59
        1,0,"CA","BOXER (D CA)",FALSE,"California",53.45
        2,0,"HI","INOUYE (D HI)",FALSE,"Hawaii",55.79
        3,1,"ID","CRAIG (R ID)",TRUE,"Idaho",27.64
        4,1,"ID","CRAPO (R ID)",TRUE,"Idaho",27.64
        5,0,"IL","DURBIN (D IL)",FALSE,"Illinois",54.6
        6,1,"IL","FITZGERALD (R IL)",TRUE,"Illinois",54.6
        7,0,"VT","LEAHY (D VT)",FALSE,"Vermont",50.63
        8,1,"VA","WARNER (R VA)",TRUE,"Virginia",44.44
        9,1,"WA","CANTWELL (D WA)",FALSE,"Washington",50.13""",
    # Air quality TSV data (with missing values)
    # Row 4: 1 NA, Row 5: 2 NA, Row 10: 3 NA
    # Mean = 23.85714, 172.62500, 12.35556. 0.66667
    # Mode (Dummy col) = 1
    'airquality_na':
        """,Ozone,Solar.R,Wind,fake_dummy
        0,41,190,7.4,0
        1,36,118,8,0
        2,12,149,12.6,0
        3,NA,313,11.5,1
        4,NA,,14.3,1
        5,28,,14.9,1
        6,23,299,8.6,1
        7,19,99,13.8,1
        8,8,19,20.1,1
        9,NA,194,NULL,n/a""",
    'airquality_imputed':
        """,Ozone,Solar.R,Wind,fake_dummy
        0,41,190,7.4,0
        1,36,118,8,0
        2,12,149,12.6,0
        3,23.85714,313,11.5,1
        4,23.85714,172.625,14.3,1
        5,28,172.625,14.9,1
        6,23,299,8.6,1
        7,19,99,13.8,1
        8,8,19,20.1,1
        9,23.85714,194,12.35556,1
        """
}

# FIXTURES

@pytest.fixture(scope='session')
def data_examples():
    return {k: pd.read_csv(StringIO(v), index_col=0) for k, v
            in STR_DATA_EXAMPLES.items()}


@pytest.mark.slow
@pytest.fixture(scope='session')
def fake_regression_data():
    """Returns Pandas DataFrame of fake regression data of size 500
    generated by the following data generating process:

    x1 ~ Normal(0, 1)
    x2 ~ Binomial(0.5)
    x3 ~ Exponential(10)
    x4 ~ Poisson(10)
    y = x1 + x2 + x3 + x4 + Normal(0, 1)
    """

    N = 500
    np.random.seed(42)
    x1 = np.random.normal(size=N)
    x2 = np.random.binomial(n=N, p=0.5)
    x3 = np.random.exponential(scale=10.0, size=N)
    x4 = np.random.poisson(lam=10, size=N)
    y = x1 + x2 + x3 + x4 + np.random.normal(size=N)

    data = pd.DataFrame({
        'x1': x1,
        'x2': x2,
        'x3': x3,
        'x4': x4,
        'y': y
    })

    return data


# UNIT TESTS

def test_column_wrangler():
    """Columns are transformed into a consistent format.
    """

    data = pd.DataFrame({
        'column1': [1, 2, 3],
        'cOLUmn2': [1, 2, 3],
        '    cOLUmn3 ': [1, 2, 3],
        ' column  4 ': [1, 2, 3],
    })
    result = _column_wrangler(data).columns
    expected = pd.Index(['column1', 'column2', 'column3', 'column_4'])
    assert_index_equal(result, expected)


def test_obj_wrangler(data_examples):
    """Columns with `object` dtype are converted to `StringDtype`.
    """

    data = data_examples['iraq_vote'].copy()
    result = _obj_wrangler(data)
    result_cols = (result.select_dtypes(include=['string'])
                         .columns)
    expected = pd.Index(['state.abb', 'name', 'state.name'])  # String columns
    assert_index_equal(result_cols, expected)


def test_factor_wrangler(data_examples):
    """Columns in `is_cat` converted to `CategoricalDtype`.
    """

    data = data_examples['iraq_vote'].copy()
    is_cat = ['state.abb', 'state.name']
    result = _factor_wrangler(data,
                              is_cat,
                              str_to_cat=False,
                              dummy_to_bool=False)
    result_cols = (result.select_dtypes(include=['category'])
                         .columns)
    expected = pd.Index(['state.abb', 'state.name'])  # Category columns
    assert_index_equal(result_cols, expected)


def test_factor_wrangler_ordered(data_examples):
    """Columns in `is_ordered` are set as ordered categorical columns.
    """

    data = data_examples['us_consump_1940s'].copy()
    # Reverse order
    data = data.iloc[::-1]
    ordered_cat_cols = ['year']
    result = _factor_wrangler(data,
                              is_cat=ordered_cat_cols,
                              is_ordered=ordered_cat_cols,
                              str_to_cat=False,
                              dummy_to_bool=False)
    result_cat = result.loc[:, 'year'].cat
    expected = pd.Index([i for i in range(1940, 1950)])
    assert_index_equal(result_cat.categories, expected)
    assert result_cat.ordered


def test_factor_wrangler_cats():
    """Columns in `categories` only contain enumerated values.
    """

    data = pd.DataFrame({
        'non_neg': [-1, 0, 1, 2, 3],
        'only_alpha': ['A#', 'B', 'C', 'D', '10'],
    })
    categories = {
        'non_neg': [0, 1, 2, 3],
        'only_alpha': ['A', 'B', 'C', 'D']
    }
    result = _factor_wrangler(data,
                              is_cat=['non_neg', 'only_alpha'],
                              categories=categories,
                              str_to_cat=False,
                              dummy_to_bool=False)
    expected = pd.DataFrame({
        'non_neg': [pd.NA, 0, 1, 2, 3],
        'only_alpha': [pd.NA, 'B', 'C', 'D', pd.NA]
    }).astype('category')
    expected.loc[:, 'only_alpha'] = (
        expected.loc[:, 'only_alpha']
        .cat
        .set_categories(categories['only_alpha'])
    )
    assert_frame_equal(result, expected)


def test_factor_wrangler_str(data_examples):
    """String columns are converted to categorical columns.
    """

    data = data_examples['iraq_vote'].copy()
    str_cols = ['state.abb', 'name', 'state.name']
    data.loc[:, str_cols] = data.loc[:, str_cols].astype('string')
    result = _factor_wrangler(data, str_to_cat=True, dummy_to_bool=False)
    res_cat_cols = (result.select_dtypes(include=['category'])
                          .columns)
    # From string to categorical columns
    expected = pd.Index(str_cols)
    assert_index_equal(res_cat_cols, expected)


def test_factor_wrangler_dummy(data_examples):
    """Dummy columns with values [0, 1] or [True, False] are converted to
    boolean columns.
    """

    data = data_examples['airquality_na'].copy()
    result = _factor_wrangler(data, dummy_to_bool=True)
    res_bool_cols = (result.select_dtypes(include=['boolean'])
                           .columns)
    # From string to categorical columns
    expected = pd.DataFrame({
        'fake_dummy': [0, 0, 0, 1, 1, 1, 1, 1, 1, pd.NA],
    }).astype('boolean')
    assert_frame_equal(result.loc[:, res_bool_cols], expected)


def test_clean_data(data_examples):
    """Smoke test.
    """

    data = data_examples['iraq_vote'].copy()
    result = clean_data.run(data)
    res_cat_cols = (result.select_dtypes(include=['category'])
                          .columns)
    res_bool_cols = (result.select_dtypes(include=['boolean'])
                           .columns)
    expected_cat_cols = pd.Index(['state.abb', 'name', 'state.name'])
    expected_bool_cols = pd.Index(['y', 'rep'])
    assert_index_equal(res_cat_cols, expected_cat_cols)
    assert_index_equal(res_bool_cols, expected_bool_cols)


def test_wrangle_na(data_examples):
    """All rows with missing values dropped from DataFrame.
    """

    data = data_examples['airquality_na'].copy()
    expected_shape = np.asarray((6, 4))
    expected = pd.Index([0, 1, 2, 6, 7, 8])
    result = wrangle_na.run(data, method='cc')
    assert_equal(expected_shape, result.shape)
    assert_index_equal(expected, result.index)


def test_wrangle_na_fi():
    """Float missing values imputed with mean value along index axis.
    Integer missing values imputed with median value along index axis.
    Categorical and boolean missing values imputed with most frequent value.
    Column dtypes are unchanged before and after.
    """

    dtypes = {'int_x': 'Int64',
              'float_x': 'float',
              'cat_x': 'category',
              'bool_x': 'boolean'}
    data = pd.DataFrame({
        'int_x': [1, 2, np.nan, 4],  # Median = 2
        'float_x': [1.5, np.nan, 2.5, 2.0],  # Mean = 2.0
        'cat_x': ['A', 'A', 'B', pd.NA],  # Most freq = 'A'
        'bool_x': [False, True, False, pd.NA]  # Most freq = False
    }).astype(dtypes)
    result = wrangle_na.run(data, method='fi')
    expected = pd.DataFrame({
        'int_x': [1, 2, 2, 4],
        'float_x': [1.5, 2.0, 2.5, 2.0],
        'cat_x': ['A', 'A', 'B', 'A'],
        'bool_x': [False, True, False, False]
    }).astype(dtypes)
    assert_frame_equal(result, expected)


def test_wrangle_na_fii():
    """Dummy columns exists for patterns of missing values across feature columns.
    Column dtypes are unchanged before and after.
    """

    dtypes = {'int_x': 'Int64',
              'float_x': 'float',
              'cat_x': 'category',
              'bool_x': 'boolean'}
    data = pd.DataFrame({
        'int_x': [1, 2, np.nan, 4],  # Median = 2
        'float_x': [1.5, np.nan, 2.5, 2.0],  # Mean = 2.0
        'cat_x': ['A', 'A', 'B', pd.NA],  # Most freq = 'A'
        'bool_x': [False, True, False, pd.NA]  # Most freq = False
    }).astype(dtypes)
    result = wrangle_na.run(data, method='fii')
    dummy_dtypes = {'na_1000': 'boolean',
                    'na_0100': 'boolean',
                    'na_0011': 'boolean'}
    expected = pd.DataFrame({
        'int_x': [1, 2, 2, 4],
        'float_x': [1.5, 2.0, 2.5, 2.0],
        'cat_x': ['A', 'A', 'B', 'A'],
        'bool_x': [False, True, False, False],
        'na_1000': [0, 0, 1, 0],
        'na_0100': [0, 1, 0, 0],
        'na_0011': [0, 0, 0, 1],
    }).astype(dtypes).astype(dummy_dtypes)
    assert_frame_equal(result, expected)


def test_wrangle_na_gm():
    """Dummy columns exists for patterns of missing values across feature columns,
    and interactions between features and missing value indicators.
    Column dtypes are unchanged before and after.
    """

    dtypes = {'int_x': 'Int64',
              'float_x': 'float',
              'cat_x': 'category',
              'bool_x': 'boolean'}
    data = pd.DataFrame({
        'int_x': [1, 2, np.nan, 4],  # Median = 2
        'float_x': [1.5, np.nan, 2.5, 2.0],  # Mean = 2.0
        'cat_x': ['A', 'A', 'B', pd.NA],  # Most freq = 'A'
        'bool_x': [False, True, False, pd.NA]  # Most freq = False
    }).astype(dtypes)
    result = wrangle_na.run(data, method='gm')
    dummy_dtypes = {'na_1000': 'boolean',
                    'na_0100': 'boolean',
                    'na_0011': 'boolean',
                    'Q("int_x"):Q("na_1000")': 'Int64',
                    'Q("int_x"):Q("na_0100")': 'Int64',
                    'Q("int_x"):Q("na_0011")': 'Int64',
                    'Q("float_x"):Q("na_1000")': 'float',
                    'Q("float_x"):Q("na_0100")': 'float',
                    'Q("float_x"):Q("na_0011")': 'float',
                    'Q("cat_x"):Q("na_1000")': 'category',
                    'Q("cat_x"):Q("na_0100")': 'category',
                    'Q("cat_x"):Q("na_0011")': 'category',
                    'Q("bool_x"):Q("na_1000")': 'boolean',
                    'Q("bool_x"):Q("na_0100")': 'boolean',
                    'Q("bool_x"):Q("na_0011")': 'boolean'}
    expected = pd.DataFrame({
        'int_x': [1, 2, 2, 4],
        'float_x': [1.5, 2.0, 2.5, 2.0],
        'cat_x': ['A', 'A', 'B', 'A'],
        'bool_x': [False, True, False, False],
        'na_1000': [0, 0, 1, 0],
        'na_0100': [0, 1, 0, 0],
        'na_0011': [0, 0, 0, 1],
        'Q("int_x"):Q("na_1000")': [1, 2, pd.NA, 4],
        'Q("int_x"):Q("na_0100")': [1, pd.NA, 2, 4],
        'Q("int_x"):Q("na_0011")': [1, 2, 2, pd.NA],
        'Q("float_x"):Q("na_1000")': [1.5, 2.0, np.nan, 2.0],
        'Q("float_x"):Q("na_0100")': [1.5, np.nan, 2.5, 2.0],
        'Q("float_x"):Q("na_0011")': [1.5, 2.0, 2.5, np.nan],
        'Q("cat_x"):Q("na_1000")': ['A', 'A', pd.NA, 'A'],
        'Q("cat_x"):Q("na_0100")': ['A', pd.NA, 'B', 'A'],
        'Q("cat_x"):Q("na_0011")': ['A', 'A', 'B', pd.NA],
        'Q("bool_x"):Q("na_1000")': [False, True, pd.NA, False],
        'Q("bool_x"):Q("na_0100")': [False, pd.NA, False, False],
        'Q("bool_x"):Q("na_0011")': [False, True, False, pd.NA],
    }).astype(dtypes).astype(dummy_dtypes)
    assert_frame_equal(result, expected)


def test_wrangle_na_mice(fake_regression_data):
    """Each MICE imputed dataset from N draws has a Kullback-Leibler (KL)
    divergence, with respect to the full original full dataset,
    that is less than 1. Column dtypes are unchanged.
    """
    pass


def test_transform_data():
    """Values in DataFrame are log transformed.
    Column dtypes are unchanged.
    """
    pass


def test_transform_data_zero():
    """Raises ValueError given zero values in DataFrame and
    transf specified as log. Column dtypes are unchanged.
    """
    pass


def test_gelman_standardize_data():
    """Numeric columns are divided by 2 s.d. and mean-centered.
    Boolean columns are shifted to have mean zero.
    All other columns are unchanged.
    """

    dtypes = {
        'float_x': 'float',
        'int_x': 'Int64',
        'bool_x': 'boolean',
        'cat_x': 'category',  # Should remain unchanged
        'string_x': 'string'  # Should remain unchanged
    }
    data = pd.DataFrame({
        'float_x': [2.2, 3.3, 1.1, 5.5, np.nan],  # mean=3.025, std=1.878607
        'int_x': [2, 3, 1, pd.NA, 5],  # mean=2.75, std=1.707925
        'bool_x': [False, False, True, True, False],  # mean = 0.4
        'cat_x': ['A', 'B', 'C', 'D', 'E'],
        'string_x': ['This', 'should', 'be', 'unchanged', '.']
    }).astype(dtypes)
    result = gelman_standardize_data.run(data)
    expected_dtypes = {
        'float_x': 'float',
        'int_x': 'float',
        'bool_x': 'float',
        'cat_x': 'category',  # Should remain unchanged
        'string_x': 'string'  # Should remain unchanged
    }
    float_x_mean, float_x_std = data['float_x'].mean(), 2*data['float_x'].std()
    int_x_mean, int_x_std = data['int_x'].mean(), 2*data['int_x'].std()
    expected = pd.DataFrame({
        'float_x': [
            (2.2-float_x_mean)/float_x_std,
            (3.3-float_x_mean)/float_x_std,
            (1.1-float_x_mean)/float_x_std,
            (5.5-float_x_mean)/float_x_std,
            np.nan
        ],
        'int_x': [
            (2-int_x_mean)/int_x_std,
            (3-int_x_mean)/int_x_std,
            (1-int_x_mean)/int_x_std,
            pd.NA,
            (5-int_x_mean)/int_x_std
        ],
        'bool_x': [-0.4, -0.4, 0.6, 0.6, -0.4],
        'cat_x': ['A', 'B', 'C', 'D', 'E'],
        'string_x': ['This', 'should', 'be', 'unchanged', '.']
    }).astype(expected_dtypes)
    assert_frame_equal(result, expected)


def test_run_model(fake_regression_data) -> alt.Chart:
    """Smoke test.
    """
    res = run_model.run(fake_regression_data,
                        y='y',
                        X=['x1', 'x2', 'x3', 'x4'])
    assert isinstance(res, RegressionResultsWrapper)


def test_plot_confidence_intervals(fake_regression_data):
    """Smoke test.
    """
    res = run_model.run(fake_regression_data,
                        y='y',
                        X=['x1', 'x2', 'x3', 'x4'])
    chart = plot_confidence_intervals.run(res)
    chart_specs = chart.to_dict()
    # Check chart width and height
    assert chart_specs['width'] == 200
    assert chart_specs['height'] == 500
    # Check chart mark
    assert chart_specs['mark'] == 'boxplot'
    # Check chart encoding keys, and corresponding fields and type
    assert chart_specs['encoding']['x']['field'] == 'regressor'
    assert chart_specs['encoding']['x']['type'] == 'ordinal'
    assert chart_specs['encoding']['y']['field'] == 'estimate'
    assert chart_specs['encoding']['y']['type'] == 'quantitative'


if __name__ == "__main__":
    pass
