import os
from elasticsearch import helpers
from v1.constant import DICTIONARY_DATA_VARIANTS
from ..utils import *
from ..constants import ELASTICSEARCH_BULK_HELPER_MESSAGE_SIZE

log_prefix = 'datastore.elastic_search.populate'


def create_all_dictionary_data(connection, index_name, doc_type, entity_data_directory_path, logger, **kwargs):
    """
    Indexes all entity data from csv files stored at entity_data_directory_path, one file at a time
    Args:
        connection: Elasticsearch client object
        index_name: The name of the index
        doc_type: The type of the documents being indexed
        logger: logging object to log at debug and exception level
        entity_data_directory_path: Path of the directory containing the entity data csv files
        kwargs:
            Refer http://elasticsearch-py.readthedocs.io/en/master/helpers.html#elasticsearch.helpers.bulk

    """
    logger.debug('%s: +++ Started: create_all_dictionary_data() +++' % log_prefix)
    if entity_data_directory_path:
        logger.debug('%s: \t== Fetching from variants/ ==' % log_prefix)
        create_dictionary_data_from_directory(connection=connection, index_name=index_name, doc_type=doc_type,
                                              entity_data_directory_path=entity_data_directory_path, update=False,
                                              logger=logger, **kwargs)
        logger.debug('%s: +++ Finished: create_all_dictionary_data() +++' % log_prefix)


def get_variants_dictionary_value_from_key(csv_file_path, dictionary_key, logger, **kwargs):
    """
    Reads the csv file at csv_file_path and create a dictionary mapping entity value to a list of their variants.
    the entity values are first column of the csv file and their corresponding variants are stored in the second column
    delimited by '|'

    Args:
        csv_file_path: absolute file path of the csv file populate entity data from
        dictionary_key: name of the entity to be put the values under
        logger: logging object to log at debug and exception level
        kwargs:
            Refer http://elasticsearch-py.readthedocs.io/en/master/helpers.html#elasticsearch.helpers.bulk

    Returns:
        Dictionary mapping entity value to a list of their variants.
    """
    dictionary_value = defaultdict(list)
    try:
        csv_reader = read_csv(csv_file_path)
        next(csv_reader)
        for data_row in csv_reader:
            try:
                data = map(str.strip, data_row[1].split('|'))
                dictionary_value[data_row[0].strip().replace('.', ' ')].extend(data)

            except Exception, e:
                logger.exception('%s: \t\t== Exception in dict creation for keyword: %s -- %s -- %s =='
                                 % (log_prefix, dictionary_key, data_row, e))

    except Exception, e:
        logger.exception(
            '%s: \t\t\t=== Exception in __get_variants_dictionary_value_from_key() Dictionary Key: %s \n %s  ===' % (
                log_prefix,
                dictionary_key, e.message))

    return dictionary_value


def add_data_elastic_search(connection, index_name, doc_type, dictionary_key, dictionary_value, logger,
                            update=False, **kwargs):
    """
    Adds all entity values and their variants to the index. Entity value and its list of variants are keys and values of
    dictionary_value parameter generated from the csv file of this entity

    Args:
        connection: Elasticsearch client object
        index_name: The name of the index
        doc_type:  The type of the documents being indexed
        dictionary_key: file name of the csv file without the extension, also used as the entity name to index values
                        of this type. Example - 'city'
        dictionary_value: dictionary, mapping entity value to a list of its variants.
                            Example - 'New Delhi': ['Delhi', 'new deli', 'New Delhi']
        logger: logging object to log at debug and exception level
        update: boolean, True if this is a update type operation, False if create/index type operation
        kwargs:
            Refer http://elasticsearch-py.readthedocs.io/en/master/helpers.html#elasticsearch.helpers.bulk

    Example of underlying index query
        {'_index': 'index_name',
         '_type': 'dictionary_data',
         'dict_type': 'variants',
         'entity_data': 'city',
         'value': 'Baripada Town'',
         'variants': ['Baripada', 'Baripada Town', '']
         '_op_type': 'index'
         }

    """
    str_query = []
    for value in dictionary_value:
        query_dict = {'_index': index_name,
                      'entity_data': dictionary_key,
                      'dict_type': DICTIONARY_DATA_VARIANTS,
                      'value': value,
                      'variants': dictionary_value[value],
                      '_type': doc_type
                      }
        if not update:
            query_dict['_op_type'] = 'index'
        str_query.append(query_dict)
        if len(str_query) > ELASTICSEARCH_BULK_HELPER_MESSAGE_SIZE:
            result = helpers.bulk(connection, str_query, stats_only=True, **kwargs)
            logger.debug('%s: \t++ %s status %s ++' % (log_prefix, dictionary_key, result))
            str_query = []
    if str_query:
        result = helpers.bulk(connection, str_query, stats_only=True, **kwargs)
        logger.debug('%s: \t++ %s status %s ++' % (log_prefix, dictionary_key, result))


def create_dictionary_data_from_file(connection, index_name, doc_type, csv_file_path, update, logger, **kwargs):
    """
    Indexes all entity data from the csv file at path csv_file_path
    Args:
        connection: Elasticsearch client object
        index_name: The name of the index
        doc_type:  The type of the documents being indexed
        csv_file_path: absolute file path of the csv file to populate entity data from
        update: boolean, True if this is a update type operation, False if create/index type operation
        logger: logging object to log at debug and exception level
        kwargs:
            Refer http://elasticsearch-py.readthedocs.io/en/master/helpers.html#elasticsearch.helpers.bulk
    """
    dictionary_key = os.path.splitext(csv_file_path)[0]
    dictionary_value = get_variants_dictionary_value_from_key(csv_file_path=csv_file_path,
                                                              dictionary_key=dictionary_key, logger=logger,
                                                              **kwargs)
    if dictionary_value:
        add_data_elastic_search(connection=connection, index_name=index_name, doc_type=doc_type,
                                dictionary_key=dictionary_key,
                                dictionary_value=remove_duplicate_data(dictionary_value),
                                update=update, logger=logger, **kwargs)
    if os.path.exists(csv_file_path) and os.path.splitext(csv_file_path)[1] == '.csv':
        os.path.basename(csv_file_path)


def create_dictionary_data_from_directory(connection, index_name, doc_type, entity_data_directory_path, update, logger,
                                          **kwargs):
    """
    Wrapper function to call create_dictionary_data_from_file() for each csv file stored in entity_data_directory_path
    Args:
        connection: Elasticsearch client object
        index_name: The name of the index
        doc_type:  The type of the documents being indexed
        entity_data_directory_path: Path of the directory containing the entity data csv files
        update: boolean, True if this is a update type operation, False if create/index type operation
        logger: logging object to log at debug and exception level
        kwargs:
            Refer http://elasticsearch-py.readthedocs.io/en/master/helpers.html#elasticsearch.helpers.bulk
    """
    csv_files = get_files_from_directory(entity_data_directory_path)
    for csv_file in csv_files:
        csv_file_path = os.path.join(entity_data_directory_path, csv_file)
        create_dictionary_data_from_file(connection=connection, index_name=index_name, doc_type=doc_type,
                                         csv_file_path=csv_file_path, update=update, logger=logger, **kwargs)
