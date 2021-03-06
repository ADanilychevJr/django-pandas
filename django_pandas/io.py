import pandas as pd
from .utils import update_with_verbose
import django
import sys
import time

def to_fields(qs, fieldnames):
    for fieldname in fieldnames:
        model = qs.model
        for fieldname_part in fieldname.split('__'):
            try:
                field = model._meta.get_field(fieldname_part)
            except django.db.models.fields.FieldDoesNotExist:
                rels = model._meta.get_all_related_objects_with_model()
                for relobj, _ in rels:
                    if relobj.get_accessor_name() == fieldname_part:
                        field = relobj.field
                        model = field.model
                        break
            else:
                if (hasattr(field, "one_to_many") and field.one_to_many) or \
                   (hasattr(field, "one_to_one") and field.one_to_one):
                    model = field.related_model
                elif field.get_internal_type() in (
                        'ForeignKey', 'OneToOneField', 'ManyToManyField'):
                    model = field.rel.to
        yield field


def is_values_queryset(qs):
    if django.VERSION < (1, 9):
        return isinstance(qs, django.db.models.query.ValuesQuerySet)
    else:
        return qs._iterable_class == django.db.models.query.ValuesIterable


def read_frame(qs, fieldnames=(), index_col=None, coerce_float=False,
               verbose=True, chunksize=1000):
    start = time.clock()
    """
    Returns a dataframe from a QuerySet

    Optionally specify the field names/columns to utilize and
    a field as the index

    Parameters
    ----------

    qs: The Django QuerySet.
    fieldnames: The model field names to use in creating the frame.
         You can span a relationship in the usual Django way
         by using  double underscores to specify a related field
         in another model
         You can span a relationship in the usual Django way
         by using  double underscores to specify a related field
         in another model

    index_col: specify the field to use  for the index. If the index
               field is not in the field list it will be appended

    coerce_float : boolean, default False
        Attempt to convert values to non-string, non-numeric data (like
        decimal.Decimal) to floating point, useful for SQL result sets

    verbose:  boolean If  this is ``True`` then populate the DataFrame with the
                human readable versions of any foreign key fields else use
                the primary keys values.
                The human readable version of the foreign key field is
                defined in the ``__unicode__`` or ``__str__``
                methods of the related class definition
   """

    if fieldnames:
        if index_col is not None and index_col not in fieldnames:
            # Add it to the field names if not already there
            fieldnames = tuple(fieldnames) + (index_col,)
        fields = to_fields(qs, fieldnames)
    elif is_values_queryset(qs):
        if django.VERSION < (1, 9):
            if django.VERSION < (1, 8):
                annotation_field_names = qs.aggregate_names
            else:
                annotation_field_names = list(qs.query.annotation_select)

            fieldnames = qs.field_names + annotation_field_names + \
                qs.extra_names
            fields = [qs.model._meta.get_field(f) for f in qs.field_names] + \
                [None] * (len(annotation_field_names) + len(qs.extra_names))

        else:
            annotation_field_names = list(qs.query.annotation_select)

            select_field_names = list(qs.query.values_select)
            extra_field_names = list(qs.query.extra_select)

            fieldnames = select_field_names + annotation_field_names \
                + extra_field_names

            fields = [qs.model._meta.get_field(f) for
                      f in select_field_names] + \
                [None] * (len(annotation_field_names) + len(extra_field_names))
    else:
        fields = qs.model._meta.fields
        fieldnames = [f.name for f in fields]

    if is_values_queryset(qs):
        recs = list(qs)
        printFlush("Not efficiently iterating bc is values queryset")
        recs2 = list(qs)
    else:
        printFlush("Chunk size (django-pandas.io): {}".format(chunksize))
        recs = list(iterateEfficiently(qs, fieldnames, chunksize=chunksize))
        
        #recs2 = list(qs.values_list(*fieldnames))

    df = pd.DataFrame.from_records(recs, columns=fieldnames,
                                   coerce_float=coerce_float)
    
    printFlush("Time taken to read frame: {} s".format(time.clock()-start))
    if verbose:
        update_with_verbose(df, fieldnames, fields)

    if index_col is not None:
        df.set_index(index_col, inplace=True)

    printFlush("Time taken to read frame AND set index: {} s".format(time.clock()-start))
    sys.stdout.flush()
    return df

def iterateEfficiently(qs, fieldnames, chunksize=1000, reverse=False):
    ordering =""
    fieldnames = ['pk'] + list(fieldnames)
    qs = qs.order_by(ordering + 'pk')
    last_pk = None
    new_items = True
    while new_items:
        new_items = False
        chunk = qs
        if last_pk is not None:
            func = 'lt' if reverse else 'gt'
            chunk = chunk.filter(**{'pk__' + func: last_pk})
        chunk = chunk[:chunksize]
        row = None
        #printFlush("iterateEfficiently!!!!")
        for row in chunk.values_list(*fieldnames):
            yield row[1:] #Don't send back the appended pk
        if row is not None:
            last_pk = row[0]
            new_items = True

def iterateEfficientlyNoFields(qs, chunksize=1000, reverse=False):
    '''Doesn't work yet'''
    ordering =""
    qs = qs.order_by(ordering + 'pk')
    last_pk = None
    new_items = True
    while new_items:
        new_items = False
        chunk = qs
        if last_pk is not None:
            func = 'lt' if reverse else 'gt'
            chunk = chunk.filter(**{'pk__' + func: last_pk})
        chunk = chunk[:chunksize]
        row = None
        for row in chunk:
            yield row
        if row is not None:
            last_pk = row.pk
            new_items = True

def printFlush(str="\nCALLED\n"):
    print str

