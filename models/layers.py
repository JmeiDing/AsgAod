import torch
import torch.nn as nn
import numpy as np
import math
import torch.nn.functional as F
from parser import parameter_parser
from torch.nn.parameter import Parameter

args = parameter_parser()


# GraphConv layers and models
class GraphConv(nn.Module):
    """
    Graph Convolution Layer & Additional tricks (power of adjacency matrix and weighted self connections)
    n_relations: number of relation types (adjacency matrices)
    """

    def __init__(self, in_features, out_features, n_relations=1,
                 activation=None, adj_sq=False, scale_identity=False):
        super(GraphConv, self).__init__()
        self.fc = nn.Linear(in_features=in_features * n_relations, out_features=out_features)
        self.n_relations = n_relations
        self.activation = activation
        self.adj_sq = adj_sq
        self.scale_identity = scale_identity

    def laplacian_batch(self, A):
        batch, N = A.shape[:2]
        if self.adj_sq:
            A = torch.bmm(A, A)  # use A^2 to increase graph connectivity
        I = torch.eye(N).unsqueeze(0).to(args.device)
        a = I.shape
        if self.scale_identity:
            I = 2 * I  # increase weight of self connections
        # A_hat = A
        # add I represents self connections of nodes
        A_hat = I + A
        # D_hat = (torch.sum(A_hat, 1) + 1e-5) ** (-0.5)  # Adjacent matrix normalization
        # L = D_hat.view(batch, N, 1) * A_hat * D_hat.view(batch, 1, N)
        L = A_hat  # remove D_hat
        return L

    def forward(self, data):
        x, A, mask = data[:3]
        if len(A.shape) == 3:
            A = A.unsqueeze(3)
        x_hat = []
        for rel in range(self.n_relations):
            x_hat.append(torch.bmm(self.laplacian_batch(A[:, :, :, rel]), x))
        x = self.fc(torch.cat(x_hat, 2))

        if len(mask.shape) == 2:
            mask = mask.unsqueeze(2)
        x = x * mask
        # to make values of dummy nodes zeros again, otherwise the bias is added after applying self.fc
        # which affects node embeddings in the following layers
        if self.activation is not None:
            x = self.activation(x)
        return x, A, mask


class GraphConvolution(nn.Module):
    """
    Simple GCN layer
    """

    def __init__(self, in_features, out_features, bias=True):
        super(GraphConvolution, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.weight = Parameter(torch.FloatTensor(in_features, out_features))
        if bias:
            self.bias = Parameter(torch.FloatTensor(out_features))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1. / math.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.uniform_(-stdv, stdv)

    def forward(self, input, adj):
        batch = input.shape[0]
        output = []
        for i in range(batch):
            if len(input.shape) == 3:
                support = torch.mm(input[i], self.weight)
                out = torch.spmm(adj[i], support)
                output.append(out.data.numpy())
            else:
                support = torch.mm(input[i], self.weight)
                out = torch.spmm(adj[i], support[i])
                output.append(out.data.numpy())
        # output = torch.mean(output, dim=0, keepdim=True)
        output = torch.from_numpy(np.array(output))
        if self.bias is not None:
            output = output + self.bias
            return output
        else:
            return output

    def __repr__(self):
        return self.__class__.__name__ + ' (' + str(self.in_features) + ' -> ' + str(self.out_features) + ')'
