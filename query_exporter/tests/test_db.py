from unittest import TestCase

from toolrack.testing.async import LoopTestCase

from .fakes import (
    FakeAsyncpg,
    FakePool)
from ..db import (
    Query,
    DataBase,
    DataBaseError,
    InvalidResultCount)


class QueryTests(TestCase):

    def test_instantiate(self):
        '''A query can be instantiated with the specified arguments.'''
        query = Query(
            'query', 20, ['db1', 'db2'], ['metric1', 'metric2'], 'SELECT 1')
        self.assertEqual(query.name, 'query')
        self.assertEqual(query.interval, 20)
        self.assertEqual(query.databases, ['db1', 'db2'])
        self.assertEqual(query.metrics, ['metric1', 'metric2'])
        self.assertEqual(query.sql, 'SELECT 1')

    def test_results(self):
        '''The results method returns a dict mapping metrics to results.'''
        query = Query('query', 20, ['db'], ['metric1', 'metric2'], 'SELECT 1')
        rows = [(11, 22), (33, 44)]
        self.assertEqual(
            query.results(rows), {'metric1': (11, 33), 'metric2': (22, 44)})

    def test_results_wrong_result_count(self):
        '''An error is raised if the result column count is wrong.'''
        query = Query('query', 20, ['db'], ['metric'], 'SELECT 1, 2')
        rows = [(1, 2)]
        with self.assertRaises(InvalidResultCount):
            query.results(rows)

    def test_results_empty(self):
        '''No error is raised if the result set is empty'''
        query = Query('query', 20, ['db'], ['metric'], 'SELECT 1, 2')
        rows = []
        self.assertEqual(query.results(rows), {})


class DataBaseTests(LoopTestCase):

    def setUp(self):
        super().setUp()
        self.db = DataBase('db', 'postgres:///foo')
        self.db.asyncpg = FakeAsyncpg()

    def test_instantiate(self):
        '''A DataBase can be instantiated with the specified arguments.'''
        self.assertEqual(self.db.name, 'db')
        self.assertEqual(self.db.dsn, 'postgres:///foo')

    async def test_connect(self):
        '''The connect connects to the database.'''
        await self.db.connect()
        self.assertIsInstance(self.db._pool, FakePool)
        self.assertEqual(self.db.asyncpg.dsn, 'postgres:///foo')

    async def test_connect_error(self):
        '''A DataBaseError is raised if database connection fails.'''
        self.db.asyncpg = FakeAsyncpg(
            connect_error='some error')
        with self.assertRaises(DataBaseError) as cm:
            await self.db.connect()
        self.assertEqual(str(cm.exception), 'some error')

    async def test_close(self):
        '''The close method closes database pool.'''
        await self.db.connect()
        pool = self.db._pool
        await self.db.close()
        self.assertTrue(pool.closed)
        self.assertIsNone(self.db._pool)

    async def test_execute(self):
        '''The execute method executes a query.'''
        query = Query('query', 20, ['db'], ['metric1', 'metric2'], 'SELECT 1')
        asyncpg = FakeAsyncpg(query_results=[(10, 20), (30, 40)])
        self.db.asyncpg = asyncpg

        await self.db.connect()
        result = await self.db.execute(query)
        self.assertEqual(result, {'metric1': (10, 30), 'metric2': (20, 40)})
        self.assertEqual(asyncpg.pool.connection.sql, 'SELECT 1')

    async def test_execute_query_error(self):
        """If the query fails an error is raised."""
        query = Query('query', 20, ['db'], ['metric'], 'WRONG')
        asyncpg = FakeAsyncpg(query_error='wrong query')
        self.db.asyncpg = asyncpg

        await self.db.connect()
        with self.assertRaises(DataBaseError) as cm:
            await self.db.execute(query)
        self.assertEqual(str(cm.exception), 'wrong query')

    async def test_execute_not_connected(self):
        """The execute recconnects to the database if not connected."""
        query = Query('query', 20, ['db'], ['metric1', 'metric2'], 'SELECT 1')
        asyncpg = FakeAsyncpg(query_results=[(10, 20), (30, 40)])
        self.db.asyncpg = asyncpg

        result = await self.db.execute(query)
        self.assertEqual(result, {'metric1': (10, 30), 'metric2': (20, 40)})
        self.assertEqual(asyncpg.pool.connection.sql, 'SELECT 1')
        # the pool is kept for reuse
        self.assertFalse(asyncpg.pool.closed)
        self.assertTrue(asyncpg.pool.connection.closed)
