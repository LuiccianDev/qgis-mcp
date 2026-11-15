"""Processing tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.helpers import checked_timeout
from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import ProcessingParams


class ProcessingToolset(BaseToolset):
    """MCP toolset for synchronous and background QGIS Processing algorithms and models."""

    domain = "processing"

    def _register_sync_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Execute Processing",
            description="Execute a QGIS Processing algorithm. Use get_algorithm_help to discover parameters. "
            "Layer params accept layer IDs or file paths. Set OUTPUT to 'memory:' for temp layers. "
            "timeout: seconds before the algorithm is cancelled (default 55). Raise it for heavy "
            "raster work, or use start_processing_job, which runs in the background with no limit. "
            "load_results: add the algorithm's outputs to the project and list them in "
            "'loaded_layers' (the processing.runAndLoadResults() behaviour). This is the only way "
            "to keep a 'TEMPORARY_OUTPUT'/'memory:' result, which is otherwise discarded when the "
            "run ends. Only vector and raster destinations are loaded, never file or folder ones. "
            "ellipsoid: ellipsoid for distance/area measurements (e.g. 'EPSG:7030' for WGS 84, "
            "'NONE' for planimetric). Default is the open project's ellipsoid.",
        )
        async def execute_processing(
            ctx: Context,
            algorithm: str,
            parameters: dict,
            timeout: int | None = None,
            load_results: bool = False,
            ellipsoid: str | None = None,
            instance: str | None = None,
        ) -> dict:
            self.validate(ProcessingParams, timeout=timeout)
            await ctx.info(f"Running algorithm: {algorithm}")
            await ctx.report_progress(0, 100)
            params: dict[str, Any] = {"algorithm": algorithm, "parameters": parameters}
            if load_results:
                params["load_results"] = True
            if ellipsoid is not None:
                params["ellipsoid"] = ellipsoid
            if timeout is None:
                socket_timeout = timeout_long
            else:
                params["timeout"] = timeout
                socket_timeout = int(timeout) + 5
            result = await _send(
                "execute_processing",
                params,
                timeout=socket_timeout,
                instance=instance,
            )
            await ctx.report_progress(100, 100)
            return result

        @mcp.tool(
            title="Start Processing Job",
            description="Run a Processing algorithm as a QGIS background task, with no time limit, "
            "and return its job id at once. QGIS stays usable while it runs. Poll "
            "get_processing_job for progress and the result; cancel_processing_job stops it. Use it "
            "instead of execute_processing for anything that may take more than a minute. Same "
            "parameters as execute_processing. A 'TEMPORARY_OUTPUT'/'memory:' vector (feature "
            "sink) output needs load_results=True, since that memory layer ends with the job; "
            "temporary files stay on disk. Algorithms that must "
            "run on QGIS's main thread are refused: use execute_processing for those.",
        )
        async def start_processing_job(
            ctx: Context,
            algorithm: str,
            parameters: dict,
            load_results: bool = False,
            ellipsoid: str | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {"algorithm": algorithm, "parameters": parameters}
            if load_results:
                params["load_results"] = True
            if ellipsoid is not None:
                params["ellipsoid"] = ellipsoid
            return await _send("start_processing_job", params, instance=instance)

        @mcp.tool(
            title="Get Processing Job",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="State of a background job: 'running' (with progress 0-100), 'succeeded' "
            "(with result, loaded_layers and warnings, as execute_processing returns them), 'failed' "
            "(with error) or 'cancelled'. Omit job_id to list every job.",
            structured_output=True,
        )
        async def get_processing_job(
            ctx: Context, job_id: str | None = None, instance: str | None = None
        ) -> dict[str, Any]:
            params = {"job_id": job_id} if job_id else {}
            return await _send("get_processing_job", params, instance=instance)

        @mcp.tool(
            title="Cancel Processing Job",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Ask a running background job to stop. Its state turns 'cancelled' once QGIS "
            "has stopped it; outputs it already wrote stay on disk.",
        )
        async def cancel_processing_job(
            ctx: Context, job_id: str, instance: str | None = None
        ) -> dict:
            return await _send("cancel_processing_job", {"job_id": job_id}, instance=instance)

    def _register_discovery_and_batch_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="List Processing Algorithms",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Search for processing algorithms by keyword and/or provider. "
            "Returns id, name, provider for each match.",
            structured_output=True,
        )
        async def list_processing_algorithms(
            ctx: Context,
            search: str | None = None,
            provider: str | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            params = {}
            if search:
                params["search"] = search
            if provider:
                params["provider"] = provider
            return await _send("list_processing_algorithms", params, instance=instance)

        @mcp.tool(
            title="Get Algorithm Help",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get detailed help for a processing algorithm: parameters (name, type, optional, default), "
            "outputs, and description.",
            structured_output=True,
        )
        async def get_algorithm_help(
            ctx: Context,
            algorithm_id: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send(
                "get_algorithm_help", {"algorithm_id": algorithm_id}, instance=instance
            )

        @mcp.tool(
            title="Get Processing Providers",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List Processing providers (native, gdal, grass, saga, model, ...) with "
            "algorithm counts and active status. Use to diagnose missing algorithms.",
            structured_output=True,
        )
        async def get_processing_providers(
            ctx: Context, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("get_processing_providers", instance=instance)

        @mcp.tool(
            title="Execute Processing Batch",
            description="Run one algorithm once per parameter dict in 'parameters_list'. "
            "Returns a per-run result with index and success/error status. Use for applying "
            "the same operation over many inputs in a single round-trip. timeout: seconds for the "
            "whole batch (default 55); runs that would start after it has elapsed come back as "
            "'skipped' with the completed ones intact, so raise it or split the list for big batches. "
            "ellipsoid: measurement ellipsoid for every run (e.g. 'EPSG:7030'); default is the project's.",
        )
        async def execute_processing_batch(
            ctx: Context,
            algorithm: str,
            parameters_list: list[dict],
            timeout: int | None = None,
            ellipsoid: str | None = None,
            instance: str | None = None,
        ) -> dict:
            await ctx.info(f"Batch processing {algorithm}: {len(parameters_list)} run(s)")
            params: dict[str, Any] = {"algorithm": algorithm, "parameters_list": parameters_list}
            if ellipsoid is not None:
                params["ellipsoid"] = ellipsoid
            if timeout is None:
                socket_timeout = timeout_long
            else:
                params["timeout"] = checked_timeout(timeout)
                socket_timeout = timeout + 5
            return await _send(
                "execute_processing_batch", params, timeout=socket_timeout, instance=instance
            )

    def _register_model_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Create Processing Model",
            description=(
                "Build QGIS Processing Model (.model3) from structured spec; save to user models folder, "
                "register in Processing Toolbox. Only call needed: algorithm discovery + param validation "
                "run in the plugin against the live registry, so do NOT call list_processing_algorithms "
                "or get_algorithm_help first. Pass keyword ('buffer') or full id ('native:buffer'); "
                "handler resolves it. Ambiguous hint returns candidate list to refine and retry. Bad "
                "param/output names reported with the valid set.\n\n"
                "Spec:\n"
                "  inputs: [{name, type, description?, default?, optional?, parent_layer? (for field/distance), "
                "options? (for enum)}]. Types: vector, feature_source, raster, field, number, integer, "
                "distance, string, boolean, extent, crs, point, file, folder, enum, multiple_layers.\n"
                "  steps: [{id, algorithm, description?, parameters: {ALG_PARAM: value}}]. algorithm = "
                "keyword or full id. Param values:\n"
                "    '@input_name'     = model input value\n"
                "    '$step_id.OUTPUT' = earlier step output\n"
                "    '=expression'     = QGIS expression at run time\n"
                "    else              = static literal (number/bool/string/list)\n"
                "  outputs: [{name, from_step, from_output, description?}] = exposed outputs; omit to "
                "expose the last step OUTPUT as 'Result'.\n\n"
                "Name collision appends a suffix (name_2.model3, ...). Response returns the actual "
                "'name', the 'requested_name', and 'resolved_steps' (which algorithm each hint mapped to)."
            ),
            structured_output=True,
        )
        async def create_processing_model(
            ctx: Context,
            name: str,
            steps: list[dict],
            inputs: list[dict] | None = None,
            outputs: list[dict] | None = None,
            description: str = "",
            group: str = "Models",
            instance: str | None = None,
        ) -> dict[str, Any]:
            await ctx.info(f"Building Processing model: {name} ({len(steps)} step(s))")
            params: dict[str, Any] = {
                "name": name,
                "steps": steps,
                "description": description,
                "group": group,
            }
            if inputs is not None:
                params["inputs"] = inputs
            if outputs is not None:
                params["outputs"] = outputs
            return await _send(
                "create_processing_model", params, timeout=timeout_long, instance=instance
            )

        @mcp.tool(
            title="List Processing Models",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List registered Processing models (the 'model' provider). "
            "Returns id, name, group for each. Use run_model to execute one.",
            structured_output=True,
        )
        async def list_processing_models(
            ctx: Context, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("list_processing_models", instance=instance)

        @mcp.tool(
            title="Run Model",
            description="Run a Processing model by registered id (e.g. 'model:myflow') or by a "
            ".model3 file path. 'parameters' maps the model's input names to values "
            "(layer ids/paths, numbers, etc.). ellipsoid: ellipsoid for distance/area measurements "
            "(e.g. 'EPSG:7030' for WGS 84, 'NONE' for planimetric); default is the project's.",
        )
        async def run_model(
            ctx: Context,
            model: str,
            parameters: dict | None = None,
            ellipsoid: str | None = None,
            instance: str | None = None,
        ) -> dict:
            await ctx.info(f"Running model: {model}")
            await ctx.report_progress(0, 100)
            params: dict[str, Any] = {"model": model, "parameters": parameters or {}}
            if ellipsoid is not None:
                params["ellipsoid"] = ellipsoid
            result = await _send(
                "run_model",
                params,
                timeout=timeout_long,
                instance=instance,
            )
            await ctx.report_progress(100, 100)
            return result

    def register(self) -> None:
        self._register_sync_tools()
        self._register_discovery_and_batch_tools()
        self._register_model_tools()
