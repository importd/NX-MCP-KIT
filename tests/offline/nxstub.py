"""Minimal NXOpen module stubs so bridge command modules import off-NX."""

import sys
import types


def install():
    nx = types.ModuleType("NXOpen")
    features = types.ModuleType("NXOpen.Features")
    gateway = types.ModuleType("NXOpen.Gateway")
    uf = types.ModuleType("NXOpen.UF")
    geo = types.ModuleType("NXOpen.GeometricUtilities")

    class Point3d:
        def __init__(self, x, y, z):
            self.X = x
            self.Y = y
            self.Z = z

    class Vector3d:
        def __init__(self, x, y, z):
            self.X = x
            self.Y = y
            self.Z = z

    class BlockFeatureBuilder:
        class Types:
            OriginAndEdgeLengths = 1

    class Feature:
        Null = None

    class BooleanFeature:
        Null = None

    class ImageExportBuilder:
        class FileFormats:
            Png = 1

        class BackgroundOptions:
            Original = 1

    class BooleanOperation:
        class BooleanType:
            Unite = 1
            Subtract = 2
            Intersect = 3

    features.BlockFeatureBuilder = BlockFeatureBuilder
    features.Feature = Feature
    features.BooleanFeature = BooleanFeature
    gateway.ImageExportBuilder = ImageExportBuilder
    uf.UFSession = type("UFSession", (), {"GetUFSession": staticmethod(lambda: None)})
    geo.BooleanOperation = BooleanOperation

    nx.Point3d = Point3d
    nx.Vector3d = Vector3d
    nx.Features = features
    nx.Gateway = gateway
    nx.UF = uf
    nx.GeometricUtilities = geo
    nx.SmartObject = type(
        "SmartObject", (), {"UpdateOption": type("U", (), {"WithinModeling": 1})}
    )

    sys.modules["NXOpen"] = nx
    sys.modules["NXOpen.Features"] = features
    sys.modules["NXOpen.Gateway"] = gateway
    sys.modules["NXOpen.UF"] = uf
    sys.modules["NXOpen.GeometricUtilities"] = geo
    return nx
