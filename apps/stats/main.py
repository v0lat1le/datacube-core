
from __future__ import absolute_import, print_function

import click
from datetime import datetime
from pathlib import Path

from datacube.api import make_mask
from datacube.model import GridSpec, CRS
from datacube.api.grid_workflow import GridWorkflow
from datacube.ui import click as ui
from datacube.utils import read_documents


def do_stats(task, config):
    source = task['source']
    measurement = source['measurements'][0]

    data = GridWorkflow.load(task['data'], measurements=[measurement])[measurement]
    data = data.where(data != data.attrs['nodata'])

    for spec, sources in zip(source['masks'], task['masks']):
        mask = GridWorkflow.load(sources, measurements=[spec['measurement']])[spec['measurement']]
        mask = make_mask(mask, **spec['flags'])
        data = data.where(mask)
        del mask

    for stat in config['stats']:
        print(getattr(data, stat['name'])(dim='time'))


def get_grid_spec(config):
    storage = config['storage']
    crs = CRS(storage['crs'])
    return GridSpec(crs=crs,
                    tile_size=[storage['tile_size'][dim] for dim in crs.dimensions],
                    resolution=[storage['resolution'][dim] for dim in crs.dimensions])


def make_tasks(index, config):
    query = dict(time=(datetime(2011, 1, 1), datetime(2011, 2, 1)))

    workflow = GridWorkflow(index, grid_spec=get_grid_spec(config))

    assert len(config['sources']) == 1  # TODO: merge multiple sources
    for source in config['sources']:
        data = workflow.list_cells(product=source['product'], cell_index=(15, -40), **query)
        masks = [workflow.list_cells(product=mask['product'], cell_index=(15, -40), **query)
                 for mask in source['masks']]

        tasks = [{
            'source': source,
            'index': key,
            'data': data[key],
            'masks': [mask[key] for mask in masks]
        } for key in data.keys()]

    return tasks


@click.command(name='stats')
@click.option('--app-config', '-c',
              type=click.Path(exists=True, readable=True, writable=False, dir_okay=False),
              help='configuration file location')
@click.option('--year', type=click.IntRange(1960, 2060))
@ui.global_cli_options
@ui.executor_cli_options
@ui.pass_index(app_name='agdc-stats')
def main(index, app_config, year, executor):
    _, config = next(read_documents(Path(app_config)))

    tasks = make_mask()

    futures = [executor.submit(do_stats, task, config) for task in tasks]
    for future in executor.as_completed(futures):
        result = executor.result(future)
        print(result)


if __name__ == '__main__':
    main()
